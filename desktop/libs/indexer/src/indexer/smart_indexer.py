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

from mako.template import Template

from hadoop import cluster

from liboozie.oozie_api import get_oozie
from liboozie.submission2 import Submission

from indexer import conf

class Indexer(object):
  # TODO: This oozie job code shouldn't be in the indexer. What's a better spot for it?
  def _upload_workspace(self, morphline):
    index_uuid = uuid.uuid4()

    hdfs_workspace_path = "/var/tmp/indexer_workspace_%s" % (index_uuid)
    hdfs_morphline_path = os.path.join(hdfs_workspace_path, "morphline.conf")
    hdfs_workflow_path = os.path.join(hdfs_workspace_path, "workflow.xml")

    workflow_template_path = os.path.join(conf.CONFIG_OOZIE_WORKSPACE_PATH.get(), "workflow.xml")

    fs = cluster.get_hdfs()

    # create workspace on hdfs
    fs.mkdir(hdfs_workspace_path)
    fs.create(hdfs_morphline_path, data=morphline)
    fs.create(hdfs_workflow_path, data=open(workflow_template_path).read())

    return hdfs_workspace_path

  def _schedule_oozie_job(self, workspace_path, collection_name, input_path):
    oozie = get_oozie("hue", api_version="v2")

    properties = {
      "dryrun":"False",
      "hue-id-w":"55",
      # TODO this shouldn't be hard coded
      "jobTracker":"hue-aaron-1.vpc.cloudera.com:8032",
      # TODO this shouldn't be hard coded
      "nameNode":"hdfs://hue-aaron-1.vpc.cloudera.com:8020",
      # TODO this shouldn't be hard coded
      "oozie.libpath":"/user/hue/smart_indexer_lib",
      "security_enabled":"False",
      "collectionName":collection_name,
      "file_path":input_path,
      "workSpacePath":workspace_path
    }
    workspace = "hdfs://hue-aaron-1.vpc.cloudera.com:8020" + workspace_path

    jobid = oozie.submit_workflow(workspace, properties)

    oozie.job_control(jobid, "start")

  def run_morphline(self, collection_name, morphline, input_path):
    workspace_path = self._upload_workspace(morphline)

    self._schedule_oozie_job(workspace_path, collection_name, input_path)

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
    return dict(file_format)

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
      "zk_host":"127.0.0.1:2181/solr"
    }

    oozie_workspace = conf.CONFIG_OOZIE_WORKSPACE_PATH.get()

    morphline_template_path = os.path.join(oozie_workspace, "morphline_template.conf")

    return Template(filename=morphline_template_path).render(**properties)

class Field(object):
  TYPE_PRIORITY = [
    'string',
    'double',
    'long',
    'int'
  ]

  @staticmethod
  def guess_type(samples):
    guesses = [Field._guess_field_type(sample) for sample in samples]

    return Field._pick_best(guesses)

  @staticmethod
  def _guess_field_type(field):
    type_ = "string"

    try:
      num = int(field)
      if isinstance(num, int):
        type_ = "int"
      elif isinstance(num, long):
        type_ = "long"
    except Exception:
      try:
        num = float(field)
        type_ = "double"
      except Exception:
        pass

    return type_

  @staticmethod
  def _pick_best(types):
    types = set(types)

    for field in Field.TYPE_PRIORITY:
      if field in types:
        return field
    return "string"

  def __init__(self, name, field_type):
    self._name = name
    self._field_type = field_type

  @property
  def name(self):
    return self._name

  @property
  def field_type(self):
    return self._field_type

  def __iter__(self):
    return {'name': self.name, 'type': self.field_type}.iteritems()

class FileFormat(object):
  @staticmethod
  def get_instance(file_stream):
    return CSVType(file_stream)

  def __init__(self):
    pass

  def format_(self):
    pass

  @property
  def fields(self):
    return []

  def __iter__(self):
    obj = {}

    obj['format'] = self.format_
    obj['columns'] = [dict(field) for field in self.fields]

    return obj.iteritems()

class CSVType(FileFormat):
  def __init__(self, file_stream):
    file_stream.seek(0)
    sample = file_stream.read(1024*1024)
    file_stream.seek(0)

    self._dialect, self._has_header = self._guess_dialect(sample)
    self._fields = self._guess_fields(sample)

    super(CSVType, self).__init__()

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

  def _guess_field_types(self, sample_rows):
    guesses = []

    for i in xrange(len(sample_rows[0])):
      samples = [sample_row[i] for sample_row in sample_rows]
      guess = Field.guess_type(samples)
      guesses.append(guess)

    return guesses

  def _get_sample_reader(self, sample):
    return csv.reader(sample.splitlines(), delimiter=self.delimiter, quotechar=self.quote_char)

  def _guess_field_names(self, sample):
    reader = self._get_sample_reader(sample)

    first_row = reader.next()

    if self._has_header:
      header = first_row
    else:
      header = ["field_%d" % (i+1) for i in range(len(first_row))]

    return header

  def _get_sample_rows(self, sample):
    NUM_SAMPLES = 5
    sample_rows = []
    reader = self._get_sample_reader(sample)

    # skip first line if it's a header
    if self._has_header:
      reader.next()

    for _ in range(NUM_SAMPLES):
      try:
        sample_rows += [reader.next()]
      except StopIteration:
        break

    return sample_rows

  def _guess_fields(self, sample):
    header = self._guess_field_names(sample)
    sample_rows = self._get_sample_rows(sample)
    types = self._guess_field_types(sample_rows)

    fields = [Field(header[i], types[i]) for i in range(len(header))]

    return fields
