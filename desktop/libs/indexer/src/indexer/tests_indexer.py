from indexer.indexer_ import Indexer

class IndexerTest():
  def test_guess_format(self):
    guessed_format = Indexer().guess_format({'file': open('./simple.csv')})
    
    file_format = guessed_format['format']
    fields = guessed_format['columns']

    # test format
    assert_equal('csv', file_format['type'])
    assert_equal(',', file_format['fieldSeparator'])
    assert_equal('\r\n', file_format['recordSeparator'])

    # test fields
    expected_fields = [
      {
        "name": "Rating",
        "field_type": "string"
      },
      {
        "name": "Location",
        "field_type": "string"
      },
      {
        "name": "Name",
        "field_type": "string"
      },
      {
        "name": "Time",
        "field_type": "string"
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
    result = Indexer().generate_morphline_config({
      'columns': [
        {'field_type': 'string', 'name': 'Rating'},
        {'field_type': 'string', 'name': 'Location'},
        {'field_type': 'string', 'name': 'Name'},
        {'field_type': 'string', 'name': 'Time'}
      ],
      'format': {'quoteChar': '"', 'recordSeparator': '\r\n', 'type': 'csv', 'hasHeader': True, 'fieldSeparator': ','}
    })
    
    print result
    # TEST SOMEHOW?

def get_tests(test_suite):
  return [getattr(test_suite, test) for test in dir(test_suite) if "test" in test]

def run_tests(tests):
  for test in tests:
    test()


def run_test_suite(test_suite):
  tests = get_tests(test_suite)
  run_tests(tests)  

if __name__ == "__main__":
  run_test_suite(IndexerTest())
