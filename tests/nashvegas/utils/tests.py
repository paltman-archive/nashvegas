from django.test import TestCase
from nashvegas.utils import get_capable_databases, get_all_migrations, \
  get_file_list

from os.path import join, dirname

mig_root = join(dirname(__import__('tests', {}, {}, [], -1).__file__), 'fixtures', 'migrations')


class GetCapableDatabasesTest(TestCase):
    def test_default_routing(self):
        results = list(get_capable_databases())
        self.assertEquals(len(results), 2)
        self.assertTrue('default' in results)
        self.assertTrue('other' in results)


class GetFileListTest(TestCase):
    def test_recursion(self):
        path = join(mig_root, 'multidb')
        results = list(get_file_list(path))
        self.assertEquals(len(results), 4)
        self.assertTrue(join(path, 'default', '0001.sql') in results)
        self.assertTrue(join(path, 'default', '0002_foo.py') in results)
        self.assertTrue(join(path, 'other', '0001.sql') in results)
        self.assertTrue(join(path, 'other', '0002_bar.sql') in results)


class GetAllMigrationsTest(TestCase):
    def test_multidb(self):
        path = join(mig_root, 'multidb')
        results = dict(get_all_migrations(path))
        self.assertEquals(len(results), 2)
        self.assertTrue('default' in results)
        self.assertTrue('other' in results)

        default = results['default']
        self.assertEquals(len(default), 2)
        self.assertTrue((1, join(path, 'default', '0001.sql')) in default)
        self.assertTrue((2, join(path, 'default', '0002_foo.py')) in default)

        other = results['other']
        self.assertEquals(len(other), 2)
        self.assertTrue((1, join(path, 'other', '0001.sql')) in other)
        self.assertTrue((2, join(path, 'other', '0002_bar.sql')) in other)
