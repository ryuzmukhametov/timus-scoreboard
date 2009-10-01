import unittest
from zope.testing import doctest, module


def test_suite():
    default_options = doctest.ELLIPSIS
    tests = unittest.TestSuite([
        doctest.DocFileSuite('utilities.txt', optionflags=default_options),
        doctest.DocFileSuite('configuration.txt', optionflags=default_options),
        doctest.DocFileSuite('crawler.txt', optionflags=default_options),
    ])
    return tests


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
