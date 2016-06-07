import json
from nose.tools import assert_equal
from mako.template import Template

class Indexer(object):
  def guess_format(self, data):
    """
    Input:
    data: {'type': 'file', 'path': '/user/hue/logs.csv'}
    Output:
    {'format': {type: 'csv', fieldSeparator : ",", recordSeparator: '\n', quoteChar : "\""}, 'columns': [{name: business_id, type: string}, {name: cool, type: integer}, {name: date, type: date}]} 
    """
    file_format = FileFormat(data['file'])

    return dict(file_format)

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

    # TODO, what to do with unique key?
    return Template(filename="./templates/schema.mako").render(fields=data['columns'])  

  @staticmethod
  def _morphline_quote_escape(string):
    return string.replace('"', '\\"')

  def generate_morphline_config(self, data):
    """
    Input:
    data: {
      'type': {'format': 'csv', 'columns': [{'name': business_id, 'included': True', 'type': 'string'}, cool, date], fieldSeparator : ",", recordSeparator: '\n', quoteChar : "\""},
      'transformation': [
        'country_code': {'replace': {'FRA': 'FR, 'CAN': 'CA'..}}
        'ip': {'geoIP': }
      ]
    } 
    Output:
    Morphline content 'SOLR_LOCATOR : { ...}' 
    """

    return Template(filename="./templates/morphline_template.conf").render(
      fields=data['columns'], 
      quote_escape=Indexer._morphline_quote_escape,
      format=data['format'])
  
  
  # def generate_indexing_job(self, collection_name, data, morphline):
  #   """
  #   Input:
  #   data: hue, 'SOLR_LOCATOR : { ...}
  #   Output:
  #   Oozie workflow
  #   """

  #   pass

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
    return {'name': self.name, 'field_type': self.field_type}.iteritems()

import csv

class FileType(object):
  def __init__(self):
    pass


class CSVType(FileType):
  def __init__(self, file_stream):
    file_stream.seek(0)
    sample = file_stream.read(1024)
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

  def _guess_field_type(self, sample_rows):
    # TODO: actually guess
    return ["string" for col in sample_rows[0]]

  def _guess_fields(self, sample):
    reader = csv.reader(sample.splitlines(), delimiter=self.delimiter, quotechar=self.quote_char)

    first_row = reader.next()


    header = first_row if self._has_header else ["field %d" % (i+1) for i in range(len(first_row))]

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

    types = self._guess_field_type(sample_rows)

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

