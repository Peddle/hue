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
# limitations under the License.from nose.tools import assert_equal
import StringIO
import logging

from nose.tools import assert_equal

from hadoop import cluster

from indexer.smart_indexer import Indexer
from indexer.controller import CollectionManagerController

LOG = logging.getLogger(__name__)

class IndexerTest():
  simpleCSVString = """id,Rating,Location,Name,Time
1,5,San Francisco,Good Restauran,t8:30pm
2,4,San Mateo,Cafe,11:30am
3,3,Berkeley,Sauls,2:30pm
"""

  def test_guess_format(self):
    stream = StringIO.StringIO(IndexerTest.simpleCSVString)

    guessed_format = Indexer("hue", None).guess_format({'file': stream})

    file_format = guessed_format['format']
    fields = guessed_format['columns']

    # test format
    assert_equal('csv', file_format['type'])
    assert_equal(',', file_format['fieldSeparator'])
    assert_equal('\r\n', file_format['recordSeparator'])

    # test fields
    expected_fields = [
      {
        "name": "id",
        "type": "int"
      },
      {
        "name": "Rating",
        "type": "int"
      },
      {
        "name": "Location",
        "type": "string"
      },
      {
        "name": "Name",
        "type": "string"
      },
      {
        "name": "Time",
        "type": "string"
      }
    ]

    assert_equal(expected_fields, fields)

  def test_end_to_end(self):
    fs = cluster.get_hdfs()
    collection_name = "test_collection"
    indexer = Indexer("hue", fs)
    input_loc = "/tmp/test.csv"

    # upload the test file to hdfs
    fs.create(input_loc, data=IndexerTest.simpleCSVString, overwrite=True)

    # open a filestream for the file on hdfs
    stream = fs.open(input_loc)

    # guess the format of the file
    format_ = indexer.guess_format({'file': stream})

    # find a field name available to use for the record's uuid
    unique_field = indexer.get_uuid_name(format_)

    # generate morphline
    morphline = indexer.generate_morphline_config(collection_name, format_, unique_field)

    schema_fields = [{"name": unique_field, "type": "string"}] + format_['columns']

    # create the collection from the specified fields
    collection_manager = CollectionManagerController("test")
    if collection_manager.collection_exists(collection_name):
      collection_manager.delete_collection(collection_name, None)
    collection_manager.create_collection(collection_name, schema_fields, unique_key_field=unique_field)

    # index the file
    indexer.run_morphline(collection_name, morphline, input_loc)
