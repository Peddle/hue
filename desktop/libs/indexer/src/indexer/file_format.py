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
import csv
import operator
import itertools
import logging

from django.utils.translation import ugettext as _

from indexer.fields import Field, guess_field_type_from_samples
from indexer.argument import TextArgument, CheckboxArgument

LOG = logging.getLogger(__name__)

def _escape_white_space_characters(s, inverse = False):
  MAPPINGS = {
    "\n":"\\n",
    "\t":"\\t",
    "\r":"\\r",
    " ":"\\s"
  }

  to = 1 if inverse else 0
  from_ = 0 if inverse else 1

  for pair in MAPPINGS.iteritems():
    s = s.replace(pair[to], pair[from_]).encode('utf-8')

  return s

def convert_format(format_dict, inverse=False):
  for field in format_dict:
    if isinstance(format_dict[field], basestring):
      format_dict[field] = _escape_white_space_characters(format_dict[field], inverse)


def get_format_types():
  return [
    CSVFormat,
    HueFormat,
    ApacheFormat,
    RubyLog,
    PostgreSqlLog,
    UnixSyslog
  ]

def get_format_prototypes():
  return [format_().get_format() for format_ in get_format_types()]

def get_format_mapping():
  return dict([(format_.get_name(), format_) for format_ in get_format_types()])

def get_file_format_instance(file, format_=None):
  file_stream = file['stream']
  file_extension = file['name'].split('.')[-1] if '.' in file['name'] else ''

  format_mapping = get_format_mapping()

  if format_ and "type" in format_:
    type_ = format_["type"]
    if type_ in format_mapping:
      if format_mapping[type_].valid_format(format_):
        return format_mapping[type_].get_instance(file_stream, format_)
      else:
        return None

  matches = [type_ for type_ in get_format_types() if file_extension in type_.get_extensions()]

  return (matches[0] if matches else get_format_types()[0]).get_instance(file_stream, format_)

class FileFormat(object):
  _name = None
  _description = None
  _customizable = True
  _args = []
  _extensions = []
  _parse_type = None

  @classmethod
  def get_extensions(cls):
    return cls._extensions

  @classmethod
  def get_name(cls):
    return cls._name

  @classmethod
  def get_parse_type(cls):
    return cls._parse_type if cls._parse_type else cls.get_name()

  @classmethod
  def get_description(cls):
    return cls._description

  @classmethod
  def get_arguments(cls):
    return cls._args

  @classmethod
  def is_customizable(cls):
    return cls._customizable

  @classmethod
  def valid_format(cls, format_):
    return format_ and all([arg.name in format_ for arg in cls.get_arguments()])

  @classmethod
  def format_info(cls):
    return {
      "name": cls.get_name(),
      "args": [arg.to_dict() for arg in cls.get_arguments()],
      "description": cls.get_description(),
      "isCustomizable": cls.is_customizable(),
      "parse_type": cls.get_parse_type()
    }

  @classmethod
  def get_instance(cls, file_stream, format_):
    return cls()

  def __init__(self):
    pass

  @property
  def sample(self):
    pass

  @property
  def fields(self):
    return []

  def get_format(self):
    return {"type": self.get_name(), "parse_type": self.get_parse_type()}

  def get_fields(self):
    obj = {}

    obj['columns'] = [field.to_dict() for field in self.fields]
    obj['sample'] = self.sample

    return obj

  def to_dict(self):
    obj = {}

    obj['format'] = self.get_format()
    obj['columns'] = [field.to_dict() for field in self.fields]
    obj['sample'] = self.sample

    return obj

class GrokkedFormat(FileFormat):
  _grok = None

  @classmethod
  def get_grok(cls):
    return cls._grok

  def get_format(self):
    format_ = super(GrokkedFormat, self).get_format()
    specific_format = {
      "grok":self.get_grok()
    }
    format_.update(specific_format)

    return format_

class HueFormat(GrokkedFormat):
  _name = "hue"
  _description = _("Hue Log File")
  _customizable = False
  _extensions = ["log"]

  def __init__(self):
    self._fields = [
      Field("date", "date"),
      Field("component", "string"),
      Field("log_level", "string"),
      Field("details", "string"),
      Field("message", "text_en"),
      Field("ip", "string"),
      Field("user", "string"),
      Field("http_method", "string"),
      Field("path", "string"),
      Field("protocol", "string")
    ]

  @property
  def fields(self):
    return self._fields

class GrokLineFormat(GrokkedFormat):
  _parse_type = "grok_line"

class ApacheFormat(GrokLineFormat):
  _name = "combined_apache"
  _description = _("Combined Apache Log File")
  _customizable = False
  _extensions = ["log"]
  _grok = "%%{COMBINEDAPACHELOG}"

  def __init__(self):
    self._fields = [
      Field("clientip", "string"),
      Field("ident", "string"),
      Field("auth", "string"),
      Field("timestamp", "date"),
      Field("verb", "string"),
      Field("request", "string"),
      Field("httpversion", "double"),
      Field("rawrequest", "long"),
      Field("response", "long"),
      Field("bytes", "long"),
      Field("referrer", "string"),
      Field("message", "text_en")
    ]

  # %{COMBINEDAPACHELOG}

  @property
  def fields(self):
    return self._fields

class RubyLog(GrokLineFormat):
  _name = "ruby_log"
  _description = _("Ruby Log")
  _customizable = False
  _extensions = ["log"]
  _grok = "%%{RUBY_LOGGER}"

  def __init__(self):
    self._fields = [
      Field("timestamp", "string"),
      Field("pid", "long"),
      Field("loglevel", "string"),
      Field("progname", "string"),
      Field("message", "text_en")
    ]

  @property
  def fields(self):
    return self._fields

class UnixSyslog(GrokLineFormat):
  _name = "syslog"
  _description = _("Linux syslog")
  _customizable = False
  _extensions = ["log"]
  _grok = "%%{SYSLOGLINE}"


  def __init__(self):
    self._fields = [
      Field("timestamp", "date"),
      Field("timestamp8601", "date"),
      Field("facility", "long"),
      Field("priority", "long"),
      Field("logsource", "string"),
      Field("program", "string"),
      Field("pid", "long"),
      Field("message", "text_en")
    ]

  @property
  def fields(self):
    return self._fields

class PostgreSqlLog(GrokLineFormat):
  _name = "postgresql_log"
  _description = _("PostgreSQL Log")
  _customizable = False
  _extensions = ["log"]
  _grok = "%%{POSTGRESQL}"


  def __init__(self):
    self._fields = [
      Field("timestamp", "date"),
      Field("user_id", "string"),
      Field("connection_id", "string"),
      Field("pid", "long")
    ]

  @property
  def fields(self):
    return self._fields

class CSVFormat(FileFormat):
  _name = "csv"
  _description = _("CSV File")
  _args = [
    TextArgument("fieldSeparator", "Field Separator"),
    TextArgument("recordSeparator", "Record Separator"),
    TextArgument("quoteChar", "Quote Character"),
    CheckboxArgument("hasHeader", "Has Header")
  ]
  _extensions = ["csv", "tsv"]

  @classmethod
  def _valid_character(self, char):
    return isinstance(char, basestring) and len(char) == 1

  @classmethod
  def _guess_dialect(cls, sample):
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(sample)
    has_header = sniffer.has_header(sample)
    return dialect, has_header

  @classmethod
  def valid_format(cls, format_):
    valid = super(CSVFormat, cls).valid_format(format_)
    valid = valid and cls._valid_character(format_["fieldSeparator"])
    valid = valid and cls._valid_character(format_["recordSeparator"])
    valid = valid and cls._valid_character(format_["quoteChar"])
    valid = valid and isinstance(format_["hasHeader"], bool)

    return valid

  @classmethod
  def _guess_from_file_stream(cls, file_stream):
    file_stream.seek(0)
    sample = '\n'.join(file_stream.read(1024*1024*5).splitlines())
    file_stream.seek(0)

    try:
      dialect, has_header = cls._guess_dialect(sample)
      delimiter = dialect.delimiter
      line_terminator = dialect.lineterminator
      quote_char = dialect.quotechar
    except Exception:
      # guess dialect failed, fall back to defaults:
      return cls()

    return cls(**{
      "delimiter":delimiter,
      "line_terminator": line_terminator,
      "quote_char": quote_char,
      "has_header": has_header,
      "sample": sample
    })

  @classmethod
  def _from_format(cls, file_stream, format_):
    file_stream.seek(0)
    sample = '\n'.join(file_stream.read(1024*1024*5).splitlines())
    file_stream.seek(0)

    delimiter = format_["fieldSeparator"].encode('utf-8')
    line_terminator = format_["recordSeparator"].encode('utf-8')
    quote_char = format_["quoteChar"].encode('utf-8')
    has_header = format_["hasHeader"]
    return cls(**{
      "delimiter":delimiter,
      "line_terminator": line_terminator,
      "quote_char": quote_char,
      "has_header": has_header,
      "sample": sample
    })

  @classmethod
  def get_instance(cls, file_stream, format_):
    if cls.valid_format(format_):
      return cls._from_format(file_stream, format_)
    else:
      return cls._guess_from_file_stream(file_stream)

  def __init__(self, delimiter=',', line_terminator='\n', quote_char='"', has_header=False, sample=""):
    self._delimiter = delimiter
    self._line_terminator = line_terminator
    self._quote_char = quote_char
    self._has_header = has_header

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

  def get_format(self):
    format_ = super(CSVFormat, self).get_format()
    specific_format = {
      "fieldSeparator":self.delimiter,
      "recordSeparator":self.line_terminator,
      "quoteChar":self.quote_char,
      "hasHeader":self._has_header
    }
    format_.update(specific_format)

    return format_

  def _guess_num_columns(self, sample_rows):
    counts = {}

    for row in sample_rows:
      num_columns = len(row)

      if num_columns not in counts:
        counts[num_columns] = 0
      counts[num_columns] += 1

    if counts:
      num_columns_guess = max(counts.iteritems(), key=operator.itemgetter(1))[0]
    else:
      num_columns_guess = 0
    return num_columns_guess

  def _guess_field_types(self, sample_rows):
    field_type_guesses = []

    num_columns = self._num_columns

    for col in range(num_columns):
      column_samples = [sample_row[col] for sample_row in sample_rows if len(sample_row) > col]

      field_type_guess = guess_field_type_from_samples(column_samples)
      field_type_guesses.append(field_type_guess)

    return field_type_guesses

  def _get_sample_reader(self, sample):
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

    if len(header) == len(types):
      # create the fields
      fields = [Field(header[i], types[i]) for i in range(len(header))]
    else:
      # likely failed to guess correctly
      LOG.warn("Guess field types failed - number of headers didn't match number of predicted types.")
      fields = []

    return fields
