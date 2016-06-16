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
import uuid
import operator
import itertools

from mako.template import Template

from liboozie.oozie_api import get_oozie
from liboozie.submission2 import Submission

from indexer.conf import CONFIG_INDEXING_TEMPLATES_PATH
from indexer.conf import zkensemble

class Indexer(object):
  def __init__(self, username, fs):
    self.fs = fs
    self.username = username

  # TODO: This oozie job code shouldn't be in the indexer. What's a better spot for it?
  def _upload_workspace(self, morphline):
    index_uuid = uuid.uuid4()

    hdfs_workspace_path = "/var/tmp/indexer_workspace_%s" % (index_uuid)
    hdfs_morphline_path = os.path.join(hdfs_workspace_path, "morphline.conf")
    hdfs_workflow_path = os.path.join(hdfs_workspace_path, "workflow.xml")

    workflow_template_path = os.path.join(CONFIG_INDEXING_TEMPLATES_PATH.get(), "workflow.xml")


    # create workspace on hdfs
    self.fs.mkdir(hdfs_workspace_path)
    self.fs.create(hdfs_morphline_path, data=morphline)
    self.fs.create(hdfs_workflow_path, data=open(workflow_template_path).read())

    return hdfs_workspace_path

  def _schedule_oozie_job(self, workspace_path, collection_name, input_path):
    oozie = get_oozie(self.username)

    workspace = "hdfs://hue-aaron-1.vpc.cloudera.com:8020" + workspace_path

    properties = {
      "dryrun": "False",
      "zkHost":  zkensemble(),
      # these libs can be installed from here:
      # https://drive.google.com/a/cloudera.com/folderview?id=0B1gZoK8Ae1xXc0sxSkpENWJ3WUU&usp=sharing
      "oozie.libpath": "/tmp/smart_indexer_lib",
      "security_enabled": "False",
      "collectionName": collection_name,
      "filePath": input_path,
      # TODO this shouldn't be hard coded either
      "outputDir": "/var/tmp/load",
      "workspacePath": workspace_path,
      'oozie.wf.application.path': workspace,
      'user.name': self.username
    }

    submission = Submission(self.username, fs=self.fs, properties=properties)
    job_id = submission.run(workspace_path)

    return job_id

  def run_morphline(self, collection_name, morphline, input_path):
    workspace_path = self._upload_workspace(morphline)

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
    return file_format.to_dict()

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

    return string

  @staticmethod
  def _get_regex_for_type(type_):
    regexes = {
      "string":".+",
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
      "fields":data['columns'],
      "format_character":Indexer._format_character,
      "uuid_name" : uuid_name,
      "get_regex":Indexer._get_regex_for_type,
      "format":data['format'],
      # TODO this shouldn't be hardcoded
      "zk_host": zkensemble()
    }

    oozie_workspace = CONFIG_INDEXING_TEMPLATES_PATH.get()

    morphline_template_path = os.path.join(oozie_workspace, "morphline_template.conf")

    return Template(filename=morphline_template_path).render(**properties)

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

  @staticmethod
  def guess_type(samples):
    guesses = [Field._guess_field_type(sample) for sample in samples]

    return Field._pick_best(guesses)

  @staticmethod
  def _guess_field_type(field):
    # TODO differentiate between text and string
    type_ = "string"

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
  def name(self):
    return self._name

  @property
  def field_type(self):
    return self._field_type

  def to_dict(self):
    return {'name': self.name, 'type': self.field_type}

class FileFormat(object):
  @staticmethod
  def get_instance(file_stream):
    return CSVFormat(file_stream)

  def __init__(self):
    pass

  def format_(self):
    pass

  @property
  def fields(self):
    return []

  def to_dict(self):
    obj = {}

    obj['format'] = self.format_
    obj['columns'] = [field.to_dict() for field in self.fields]

    return obj

class CSVFormat(FileFormat):
  def __init__(self, file_stream):
    file_stream.seek(0)
    sample = file_stream.read(1024*1024*5)
    file_stream.seek(0)

    self._dialect, self._has_header = self._guess_dialect(sample)

    self._sample_rows = self._get_sample_rows(sample)
    self._num_columns = self._guess_num_columns(self._sample_rows)

    self._fields = self._guess_fields(sample)

    super(CSVFormat, self).__init__()

  @property
  def fields(self):
    return self._fields

  @property
  def delimiter(self):
    return self._dialect.delimiter

  @property
  def line_terminator(self):
    return self._dialect.lineterminator

  @property
  def quote_char(self):
    return self._dialect.quotechar

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

    num_columns_guess = max(counts.iteritems(), key=operator.itemgetter(1))[0]
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
    return csv.reader(sample.splitlines(), delimiter=self.delimiter, quotechar=self.quote_char)

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
    reader = itertools.islice(self._get_sample_reader(sample), header_offset + 1, NUM_SAMPLES + 1)

    sample_rows = list(reader)
    return sample_rows

  def _guess_fields(self, sample):
    header = self._guess_field_names(sample)
    types = self._guess_field_types(self._sample_rows)

    fields = [Field(header[i], types[i]) for i in range(len(header))]

    return fields
