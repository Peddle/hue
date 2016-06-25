# Licensed to Cloudera, Inc. under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  Cloudera, Inc. licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.import logging
import os
import csv
import operator
import itertools

from mako.lookup import TemplateLookup
from mako.template import Template

from liboozie.oozie_api import get_oozie
from oozie.models2 import Job
from liboozie.submission2 import Submission

from indexer.conf import CONFIG_INDEXING_TEMPLATES_PATH
from indexer.conf import zkensemble

from collections import deque

class Indexer(object):
  def __init__(self, username, fs):
    self.fs = fs
    self.username = username

  # TODO: This oozie job code shouldn't be in the indexer. What's a better spot for it?
  def _upload_workspace(self, morphline):
    # index_uuid = uuid.uuid4()

    # hdfs_workspace_path = "/var/tmp/indexer_workspace_%s" % (index_uuid)
    hdfs_workspace_path = Job.get_workspace(self.username)
    hdfs_morphline_path = os.path.join(hdfs_workspace_path, "morphline.conf")
    hdfs_workflow_path = os.path.join(hdfs_workspace_path, "workflow.xml")
    hdfs_log4j_properties_path = os.path.join(hdfs_workspace_path, "log4j.properties")
    hdfs_grok_patterns_path = os.path.join(hdfs_workspace_path, "grok-patterns.txt")

    workflow_template_path = os.path.join(CONFIG_INDEXING_TEMPLATES_PATH.get(), "workflow.xml")
    log4j_template_path = os.path.join(CONFIG_INDEXING_TEMPLATES_PATH.get(), "log4j.properties")
    grok_patterns_path = os.path.join(CONFIG_INDEXING_TEMPLATES_PATH.get(), "grok-patterns.txt")

    # create workspace on hdfs
    self.fs.do_as_user(self.username,  self.fs.mkdir, hdfs_workspace_path)

    self.fs.do_as_user(self.username,  self.fs.create, hdfs_morphline_path, data=morphline)
    self.fs.do_as_user(self.username,  self.fs.create, hdfs_workflow_path, data=open(workflow_template_path).read())
    self.fs.do_as_user(self.username,  self.fs.create, hdfs_log4j_properties_path, data=open(log4j_template_path).read())
    self.fs.do_as_user(self.username,  self.fs.create, hdfs_grok_patterns_path, data=open(grok_patterns_path).read())

    return hdfs_workspace_path

  def _schedule_oozie_job(self, workspace_path, collection_name, input_path):
    oozie = get_oozie(self.username)


    properties = {
      "dryrun": "False",
      "zkHost":  zkensemble(),
      # TODO this can be removed once workflow bug is fixed
      "hue-id-w": "55",
      # these libs can be installed from here:
      # https://drive.google.com/a/cloudera.com/folderview?id=0B1gZoK8Ae1xXc0sxSkpENWJ3WUU&usp=sharing
      "oozie.libpath": "/tmp/smart_indexer_lib",
      "security_enabled": "False",
      "collectionName": collection_name,
      "filePath": input_path,
      # TODO this shouldn't be hard coded either
      "outputDir": "/user/%s/indexer" % self.username,
      "workspacePath": workspace_path,
      'oozie.wf.application.path': "${nameNode}%s" % workspace_path,
      'user.name': self.username
    }

    submission = Submission(self.username, fs=self.fs, properties=properties)
    job_id = submission.run(workspace_path)

    return job_id

  def run_morphline(self, collection_name, morphline, input_path):
    workspace_path = self._upload_workspace(morphline)

    print "DEBUG=========================\n%s\n========================" % workspace_path

    job_id = self._schedule_oozie_job(workspace_path, collection_name, input_path)
    return job_id

  def guess_format(self, data):
    """
    Input:
    data: {'type': 'file', 'path': '/user/hue/logs.csv'}
    Output:
    {'format':
      {
        type: 'csv',
        fieldSeparator : ",",
        recordSeparator: '\n',
        quoteChar : "\""
      },
      'columns':
        [
          {name: business_id, type: string},
          {name: cool, type: integer},
          {name: date, type: date}
          ]
    }
    """
    file_format = FileFormat.get_instance(data['file'])
    return file_format.get_format()

  def guess_field_types(self, data):
    file_format = FileFormat.get_instance(data['file'], data['format'])
    return file_format.get_fields()

  # Breadth first ordering of fields
  def get_field_list(self, field_data):
    fields = []

    queue = deque(field_data)

    while len(queue):
      curr_field = queue.popleft()
      fields.append(curr_field)

      for operation in curr_field["operations"]:
        for field in operation["fields"]:
          queue.append(field)

    return fields

  def get_kept_field_list(self, field_data):
    return [field for field in self.get_field_list(field_data) if field['keep']]

  def get_uuid_name(self, format_):
    base_name = "_uuid"

    field_names = set([column['name'] for column in format_['columns']])

    while base_name in field_names:
      base_name = '_' + base_name

    return base_name

  @staticmethod
  def _format_character(string):
    string = string.replace('\\', '\\\\')
    string = string.replace('"', '\\"')
    string = string.replace('\t', '\\t')
    string = string.replace('\n', '\\n')

    return string

  @staticmethod
  def _get_regex_for_type(type_):
    regexes = {
      "string":".*",
      "text":".*",
      "int": "(?:[+-]?(?:[0-9]+))", #TODO: differentiate between ints and longs
      "long": "(?:[+-]?(?:[0-9]+))",
      "double": "(?<![0-9.+-])(?>[+-]?(?:(?:[0-9]+(?:\\.[0-9]+)?)|(?:\\.[0-9]+)))"
    }

    return regexes[type_].replace('\\', '\\\\')

  def generate_morphline_config(self, collection_name, data, uuid_name):
    """
    Input:
    data: {
      'type': {'name': 'My New Collection!' format': 'csv', 'columns': [{'name': business_id, 'included': True', 'type': 'string'}, cool, date], fieldSeparator : ",", recordSeparator: '\n', quoteChar : "\""},
      'transformation': [
        'country_code': {'replace': {'FRA': 'FR, 'CAN': 'CA'..}}
        'ip': {'geoIP': }
      ]
    }
    Output:
    Morphline content 'SOLR_LOCATOR : { ...}'
    """

    properties = {
      "collection_name":collection_name,
      "fields":self.get_field_list(data['columns']),
      "num_base_fields": len(data['columns']),
      "format_character":Indexer._format_character,
      "uuid_name" : uuid_name,
      "get_regex":Indexer._get_regex_for_type,
      "format":data['format'],
      "grok_dictionaries_location" : "/tmp/smart_indexer_lib/grok_dictionaries",
      # TODO this shouldn't be hardcoded
      "zk_host": zkensemble()
    }

    print properties['fields']

    oozie_workspace = CONFIG_INDEXING_TEMPLATES_PATH.get()

    # morphline_template_path = os.path.join(oozie_workspace, "morphline_template.conf")

    lookup = TemplateLookup(directories=[oozie_workspace])
    morphline = lookup.get_template("morphline_template.conf").render(**properties)
    # morphline = Template(filename=morphline_template_path, lookup=lookup).render(**properties)


    return morphline

class Field(object):
  TYPE_PRIORITY = [
    'string',
    'double',
    'long',
    'int'
  ]

  def __init__(self, name, field_type):
    self._name = name
    self._field_type = field_type
    self._keep = True
    self._operations = []
    self._required = True

  @staticmethod
  def guess_type(samples):
    guesses = [Field._guess_field_type(sample) for sample in samples]

    return Field._pick_best(guesses)

  @staticmethod
  def _guess_field_type(field):
    # TODO differentiate between text and string
    STRING_THRESHOLD = 100
    type_ = "string" if len(field) < STRING_THRESHOLD else "text"

    try:
      num = int(field)
      if isinstance(num, int):
        type_ = "int"
      elif isinstance(num, long):
        type_ = "long"
    except ValueError:
      try:
        num = float(field)
        type_ = "double"
      except ValueError:
        pass

    return type_

  @staticmethod
  def _pick_best(types):
    types = set(types)

    for field in Field.TYPE_PRIORITY:
      if field in types:
        return field
    return "string"

  @property
  def required(self):
    return self._required
  

  @property
  def name(self):
    return self._name

  @property
  def field_type(self):
    return self._field_type

  @property
  def keep(self):
    return self._keep
  
  @property
  def operations(self):
    return self._operations
  

  def to_dict(self):
    return {'name': self.name, 
    'type': self.field_type, 
    'keep': self.keep, 
    'operations': self.operations,
    'required': self.required}

class FileFormat(object):
  @staticmethod
  def get_instance(file_stream, format_=None):
    return CSVFormat(file_stream, format_)

  def __init__(self):
    pass

  @property
  def format_(self):
    pass

  @property
  def sample(self):
    pass
  

  @property
  def fields(self):
    return []

  def get_format(self):
    return self.format_

  def get_fields(self):
    obj = {}

    obj['columns'] = [field.to_dict() for field in self.fields]
    obj['sample'] = self.sample

    return obj

  def to_dict(self):
    obj = {}

    obj['format'] = self.format_
    obj['columns'] = [field.to_dict() for field in self.fields]
    obj['sample'] = self.sample

    return obj

class CSVFormat(FileFormat):
  def __init__(self, file_stream, format_=None):
    file_stream.seek(0)
    sample = file_stream.read(1024*1024*5)
    file_stream.seek(0)

    if format_:
      self._delimiter = format_["fieldSeparator"].encode('utf-8')
      self._line_terminator = format_["recordSeparator"].encode('utf-8')
      self._quote_char = format_["quoteChar"].encode('utf-8')
      self._has_header = format_["hasHeader"]
    else:
      dialect, self._has_header = self._guess_dialect(sample)
      self._delimiter = dialect.delimiter
      self._line_terminator = dialect.lineterminator
      self._quote_char = dialect.quotechar

    # sniffer insists on \r\n even when \n. This is safer and good enough for a preview
    self._line_terminator = self._line_terminator.replace("\r\n", "\n")

    self._sample_rows = self._get_sample_rows(sample)
    self._num_columns = self._guess_num_columns(self._sample_rows)

    self._fields = self._guess_fields(sample)

    super(CSVFormat, self).__init__()

  @property
  def sample(self):
    return self._sample_rows

  @property
  def fields(self):
    return self._fields

  @property
  def delimiter(self):
    return self._delimiter

  @property
  def line_terminator(self):
    return self._line_terminator

  @property
  def quote_char(self):
    return self._quote_char

  @property
  def format_(self):
    return {
      "type":"csv",
      "fieldSeparator":self.delimiter,
      "recordSeparator":self.line_terminator,
      "quoteChar":self.quote_char,
      "hasHeader":self._has_header
    }

  def _guess_dialect(self, sample):
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(sample)
    has_header = sniffer.has_header(sample)
    return dialect, has_header

  def _guess_num_columns(self, sample_rows):
    counts = {}

    for row in sample_rows:
      num_columns = len(row)

      if num_columns not in counts:
        counts[num_columns] = 0
      counts[num_columns] += 1

    if len(counts):
      num_columns_guess = max(counts.iteritems(), key=operator.itemgetter(1))[0]
    else:
      num_columns_guess = 0
    return num_columns_guess

  def _guess_field_types(self, sample_rows):
    field_type_guesses = []

    num_columns = self._num_columns

    for col in range(num_columns):
      column_samples = [sample_row[col] for sample_row in sample_rows if len(sample_row) > col]

      field_type_guess = Field.guess_type(column_samples)
      field_type_guesses.append(field_type_guess)

    return field_type_guesses

  def _get_sample_reader(self, sample):
    print [self.line_terminator]
    if self.line_terminator != '\n':
      sample = sample.replace('\n', '\\n')
    return csv.reader(sample.split(self.line_terminator), delimiter=self.delimiter, quotechar=self.quote_char)

  def _guess_field_names(self, sample):
    reader = self._get_sample_reader(sample)

    first_row = reader.next()

    if self._has_header:
      header = first_row
    else:
      header = ["field_%d" % (i+1) for i in range(self._num_columns)]

    return header

  def _get_sample_rows(self, sample):
    NUM_SAMPLES = 5

    header_offset = 1 if self._has_header else 0
    reader = itertools.islice(self._get_sample_reader(sample), header_offset, NUM_SAMPLES + 1)

    sample_rows = list(reader)
    return sample_rows

  def _guess_fields(self, sample):
    header = self._guess_field_names(sample)
    types = self._guess_field_types(self._sample_rows)

    print header
    print types

    if len(header) == len(types):
      fields = [Field(header[i], types[i]) for i in range(len(header))]
    else:
      # likely failed to guess correctly
      fields = []

    return fields
