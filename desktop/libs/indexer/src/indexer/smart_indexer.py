import json
import logging
from mako.template import Template
from hadoop import cluster
from liboozie.oozie_api import get_oozie
from liboozie.submission2 import Submission

LOG = logging.getLogger(__name__)



class Indexer(object):
  def run_morphline(self, collection_name, morphline, input_path):
    fs = cluster.get_hdfs()

    LOG.info(morphline)

    # TODO put this in tmp and clean up after
    fs.create("/user/hue/uploaded_morphline.conf",
      overwrite=True,
      data=morphline
      )

    oozie = get_oozie("admin", api_version="v2")

    # TODO these shouldn't be hardcoded
    properties = {
      "dryrun":"False",
      "hue-id-w":"55",
      "jobTracker":"hue-aaron-1.vpc.cloudera.com:8032",
      "nameNode":"hdfs://hue-aaron-1.vpc.cloudera.com:8020",
      "oozie.use.system.libpath":"True",
      "security_enabled":"False",
      "collectionName":collection_name,
      "file_path":input_path
    }
    workspace = "hdfs://hue-aaron-1.vpc.cloudera.com:8020/user/hue/hue_smart_index_workspace"

    jobid = oozie.submit_workflow(
      workspace, 
      properties)

    oozie.job_control(jobid, "start")

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
    file_format = FileFormat(data['file'])

    return dict(file_format)

  def get_uuid_name(self, format_):
    base_name = "_uuid"

    field_names = set([column['name'] for column in format_['columns']])

    while base_name in field_names:
      base_name = '_' + base_name

    return base_name

  def generate_solr_schema(self, data):
    # TODO: schema should be based off of user input. Why read from path again?
    """
    Input: {'columns': [{name: business_id, type: string}, {name: cool, type: integer}, {name: date, type: date}]}
    data: {'type': 'file', 'path': '/user/hue/logs.csv'}
    Output:
    schema.xml
    default field 'df'
    """

    """
    SchemaBuilder
    """

    # Load schema
    schemaTemplate =  Template(filename="./desktop/libs/indexer/src/indexer/templates/schema.mako")


    # TODO, what to do with unique key?
    return schemaTemplate.render(fields=data['columns'])  

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
      "int": "(?:[+-]?(?:[0-9]+))",
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
    # TODO what happens if there is a space in a field name? is that allowed by the spec? 
      # if so how does mako handle it?
    # TODO use conf.py in indexer to (indexer.conf) to store the file location
    return Template(filename="./desktop/libs/indexer/src/indexer/templates/morphline_template.conf").render(
      collection_name=collection_name,
      fields=data['columns'],
      format_character=Indexer._format_character,
      uuid_name = uuid_name,
      get_regex=Indexer._get_regex_for_type,
      format=data['format'])
    
  def generate_indexing_job(self, data, morphline):
    """
    Input:
    data: hue, 'SOLR_LOCATOR : { ...}
    Output:
    Oozie workflow
    """

    pass

# TODO: is using a field class over desigining?
class Field(object):
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

import csv

class FileType(object):
  def __init__(self):
    pass


class CSVType(FileType):
  def __init__(self, file_stream):
    file_stream.seek(0)
    sample = file_stream.read(1024*1024)
    file_stream.seek(0)

    self._dialect, self._has_header = self._guess_dialect(sample)
    self._fields = self._guess_fields(sample)

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
  

  def _guess_dialect(self, sample):
    # TODO: put some thought into how much to sniff
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(sample)
    has_header = sniffer.has_header(sample)

    # TODO: will probably want to return more information than just the quotechar and the delimiter
    # TODO: why not just store dialect object?
    return dialect, has_header

  def _guess_field_type(self, field):
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

  def _pick_best(self, types):
    if "string" in types:
      return "string"
    elif "double" in types:
      return "double"
    elif "long" in types:
      return "long"
    else:
      return "int"

  def _guess_field_types(self, sample_rows):
    all_guesses = [set() for _ in range(len(sample_rows[0]))]

    for row in sample_rows:
      row_guesses = [self._guess_field_type(col) for col in row]

      for col in range(len(row_guesses)):
        all_guesses[col].add(row_guesses[col])

    return [self._pick_best(types) for types in all_guesses]

  def _guess_fields(self, sample):
    reader = csv.reader(sample.splitlines(), delimiter=self.delimiter, quotechar=self.quote_char)

    first_row = reader.next()


    header = first_row if self._has_header else [\
      "field_%d" % (i+1)\
      for i in range(len(first_row))]

    # TODO: keep first_row or lazily throw away?
    # TODO: put some thought into the number of sample rows
    # TODO: what if the csv has less than number of sample rows wanted
    # sample_rows = [reader.next() for i in range(5)]

    sample_rows = []
    num_rows_needed = 5 - 0 if self._has_header else 1

    for i in range(num_rows_needed):
      try:
        sample_rows += [reader.next()]
      except StopIteration:
        break

    types = self._guess_field_types(sample_rows)

    # TODO: replace this with elegant error handling
    assert len(header) == len(types)

    fields = [Field(header[i], types[i]) for i in range(len(header))]

    return fields

  def __iter__(self):
    return {
      "type":"csv",
      "fieldSeparator":self.delimiter,
      "recordSeparator":self.line_terminator,
      "quoteChar":self.quote_char,
      "hasHeader":self._has_header
    }.iteritems()

# TODO: is this class even necessary?
class FileFormat(object):
  def __init__(self, file):
    self._file = file
    self._file_type = self._guess_file_type()



  def _guess_file_type(self):
    # TODO: actually guess the file type and don't just assume CSV
    return CSVType(self._file)


  def fields(self):
    return self._file_type.fields


  def __iter__(self):
    obj = {}

    obj['format'] = dict(self._file_type)
    obj['columns'] = [dict(field) for field in self.fields()]


    return obj.iteritems()

