from nose.tools import assert_equal
import StringIO
import logging
from indexer.smart_indexer import Indexer
from indexer.controller import CollectionManagerController


LOG = logging.getLogger(__name__)

class IndexerTest():
  simpleCSVString = """id,Rating,Location,Name,Time
1,5,San Francisco,Good Restauran,t8:30pm
2,4,San Mateo,Cafe,11:30am
3,3,Berkeley,Sauls,2:30pm
"""
  def test_run_morphline(self):
    Indexer().run_morphline("test_collection", "not a real morphline")

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

  # TODO: this test is very brittle and not ideal. Probably don't even want to bother with tests for this
  def test_generate_schema(self):
    # result = Indexer().generate_solr_schema({'columns': [
    #   {'field_type': 'string', 'name': 'Rating'},
    #   {'field_type': 'string', 'name': 'Location'},
    #   {'field_type': 'string', 'name': 'Name'},
    #   {'field_type': 'string', 'name': 'Time'}],
    # }).encode("utf-8")
    # assert_equal(open('./expected_schema.txt').read(), result)
    pass

    # print open('./expected_schema.txt').read()


  def test_generate_morphline(self):
    result = Indexer().generate_morphline_config('test_collection', {
      'columns': [
        {'type': 'string', 'name': 'Rating'},
        {'type': 'string', 'name': 'Location'},
        {'type': 'string', 'name': 'Name'},
        {'type': 'string', 'name': 'Time'}
      ],
      'format': {'quoteChar': '"', 'recordSeparator': '\r\n', 'type': 'csv', 'hasHeader': True, 'fieldSeparator': ','}
    })
    
    LOG.info(result)
    # TEST SOMEHOW?


  def test_end_to_end(self):
    collection_name = "taxi_data_2"
    indexer = Indexer()
    input_loc = "/tmp/taxi_data.csv"

    # stream = StringIO.StringIO(IndexerTest.simpleCSVString)
    # stream = open("/home/aaronpeddle/Downloads/commits.tsv")
    from hadoop import cluster
    stream = cluster.get_hdfs().open(input_loc)

    format_ = indexer.guess_format({'file': stream})
    
    unique_field = indexer.get_uuid_name(format_)
    print "Unique Field: " + unique_field 


    # this has already benn done
    # schema = indexer.generate_solr_schema(format_)

    morphline = indexer.generate_morphline_config(collection_name,format_, unique_field)


    # # job = Submission('hue').run(deployment_dir="/user/hue/oozie/workspaces/hue-oozie-1465324937.64")
    # # can probably just call old
    # # indexer.create_solr_collection(collection_name, schema)

    # TODO rename to fields to fit in with controller2 convention
    CollectionManagerController("solr").\
      create_collection(collection_name, [{"name": unique_field, "type": "string"}] + format_['columns'], unique_key_field=unique_field)

    # indexer.generate_indexing_job(morphline)

    indexer.run_morphline(collection_name, morphline, input_loc)

    # TODO add cleanup here

    # LOG.info(oozie.get_workflows(filters=[('name', 'JavaIndexerTest')]).jobs.appName)



# def get_tests(test_suite):
#   return [getattr(test_suite, test) for test in dir(test_suite) if "test" in test]

# def run_tests(tests):
#   for test in tests:
#     test()


# def run_test_suite(test_suite):
#   tests = get_tests(test_suite)
#   run_tests(tests)

# if __name__ == "__main__":
#   run_test_suite(IndexerTest())
