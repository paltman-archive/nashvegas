import mock
from django.test import TestCase
from nashvegas.utils import get_capable_databases, get_all_migrations, \
  get_file_list, get_pending_migrations
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


class GetPendingMigrationsTest(TestCase):
    @mock.patch('nashvegas.utils.get_all_migrations')
    @mock.patch('nashvegas.utils.get_applied_migrations')
    def test_handles_duplicate_migration_numbers(self, get_applied_migrations, get_all_migrations):
        get_applied_migrations.return_value = {
            'dupes': ['0001.sql', '0002_foo.sql'],
        }
        get_all_migrations.return_value = {
            'dupes': [(1, '0001.sql'), (2, '0002_bar.sql'), (2, '0002_foo.sql')],
        }

        path = join(mig_root, 'multidb')
        results = dict(get_pending_migrations(path))

        get_applied_migrations.assert_called_once_with(None)
        get_all_migrations.assert_called_once_with(path, None)

        self.assertEquals(len(results), 1)
        self.assertTrue('dupes' in results)
        self.assertEquals(len(results['dupes']), 1)
        self.assertTrue('0002_bar.sql' in results['dupes'])
