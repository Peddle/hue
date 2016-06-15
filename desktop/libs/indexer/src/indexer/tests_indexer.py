from nose.tools import assert_equal
import StringIO
import logging
from indexer.smart_indexer import Indexer
from indexer.controller import CollectionManagerController
from hadoop import cluster # used for integration test

LOG = logging.getLogger(__name__)

class IndexerTest():
  simpleCSVString = """id,Rating,Location,Name,Time
1,5,San Francisco,Good Restauran,t8:30pm
2,4,San Mateo,Cafe,11:30am
3,3,Berkeley,Sauls,2:30pm
"""

  def test_guess_format(self):
    stream = StringIO.StringIO(IndexerTest.simpleCSVString)

    guessed_format = Indexer().guess_format({'file': stream})
    
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
    collection_name = "test_collection"
    indexer = Indexer()
    input_loc = "/tmp/test2.csv"

    # open a filestream for the file on hdfs
    stream = cluster.get_hdfs().open(input_loc)

    # guess the format of the file
    format_ = indexer.guess_format({'file': stream})
    
    # find a field name available to use for the record's uuid
    unique_field = indexer.get_uuid_name(format_)

    # generate morphline
    morphline = indexer.generate_morphline_config(collection_name, format_, unique_field)

    schema_fields = [{"name": unique_field, "type": "string"}] + format_['columns']

    # create the collection from the specified fields
    CollectionManagerController("solr").\
      create_collection(collection_name, schema_fields, unique_key_field=unique_field)

    # index the file
    indexer.run_morphline(collection_name, morphline, input_loc)
