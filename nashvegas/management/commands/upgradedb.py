import os
import re
import sys
import traceback

from optparse import make_option
from subprocess import Popen, PIPE

from django.db import connections, transaction, DEFAULT_DB_ALIAS
from django.db.models import get_model
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.sql import emit_post_sync_signal
from django.utils.importlib import import_module

from nashvegas.exceptions import MigrationError
from nashvegas.models import Migration
from nashvegas.utils import get_sql_for_new_models, get_capable_databases, \
  get_pending_migrations


sys.path.append("migrations")
MIGRATION_NAME_RE = re.compile(r"(\d+)(.*)")


class Transactional(object):
    def __enter__(self):
        for db in connections:
            # enter transaction management
            transaction.enter_transaction_management(using=db)
            transaction.managed(True, using=db)
    
    def __exit__(self, exc_type, exc_value, traceback):
        for db in connections:
            if exc_type:
                transaction.rollback(using=db)
            else:
                transaction.commit(using=db)
            transaction.leave_transaction_management(using=db)


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option("-l", "--list", action="store_true",
                    dest="do_list", default=False,
                    help="Enumerate the list of migrations to execute."),
        make_option("-e", "--execute", action="store_true",
                    dest="do_execute", default=False,
                    help="Execute migrations not in versions table."),
        make_option("-c", "--create", action="store_true",
                    dest="do_create", default=False,
                    help="Generates sql for models that are installed but not in your database."),
        make_option("--create-all", action="store_true",
                    dest="do_create_all", default=False,
                    help="Generates sql for models that are installed but not in your database."),
        make_option("-s", "--seed", action="store_true",
                    dest="do_seed", default=False,
                    help="Seed nashvegas with migrations that have previously been applied in another manner."),
        make_option("-d", "--database", action="append", dest="databases",
                    help="Nominates a database to synchronize."),
        make_option("--noinput", action="store_false", dest="interactive", default=False,
                    help="Tells Django to NOT prompt the user for input of any kind."),
        make_option("-p", "--path", dest="path",
                    default=None,
                    help="The path to the database migration scripts."))
    
    help = "Upgrade database."
    
    def _get_rev(self, fpath):
        """
        Get an SCM version number. Try svn and git.
        """
        rev = None
        
        try:
            cmd = ["git", "log", "-n1", "--pretty=format:\"%h\"", fpath]
            rev = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()[0]
        except:
            pass
        
        if not rev:
            try:
                cmd = ["svn", "info", fpath]
                svninfo = Popen(cmd, stdout=PIPE, stderr=PIPE).stdout.readlines()
                for info in svninfo:
                    tokens = info.split(":")
                    if tokens[0].strip() == "Last Changed Rev":
                        rev = tokens[1].strip()
            except:
                pass
        
        return rev
    
    def _get_current_migration_number(self, database):
        try:
            result = Migration.objects.using(database).order_by('-migration_label')[0]
        except IndexError:
            return 0
        match = MIGRATION_NAME_RE.match(result.migration_label)
        return int(match.group(1))
    
    def _get_migration_path(self, db, migration):
        if db == DEFAULT_DB_ALIAS and os.path.exists(os.path.join(self.path, migration)):
            migration_path = os.path.join(self.path, migration)
        else:
            migration_path = os.path.join(self.path, db, migration)

        return migration_path
    
    def _execute_migration(self, database, migration, show_traceback=True):
        created_models = set()
        
        with open(migration, "rb") as fp:
            lines = fp.readlines()
        content = "".join(lines)
        
        if migration.endswith(".sql"):
            # TODO: this should support proper comments
            to_execute = "".join(
                [l for l in lines if not l.startswith("### New Model: ")]
            )
            connection = connections[database]
            cursor = connection.cursor()
            
            try:
                cursor.execute(to_execute)
                cursor.close()
            except Exception:
                sys.stdout.write("failed\n")
                if show_traceback:
                    traceback.print_exc()
                raise MigrationError()
            else:
                sys.stdout.write("success\n")
            
            for l in lines:
                if l.startswith("### New Model: "):
                    created_models.add(
                        get_model(
                            *l.replace("### New Model: ", "").strip().split(".")
                        )
                    )
        
        elif migration.endswith(".py"):
            # TODO: python files have no concept of active database
            #       we should probably pass it to migrate()
            module = {}
            execfile(migration, {}, module)
            
            if "migrate" in module and callable(module["migrate"]):
                try:
                    module["migrate"]()
                except Exception:
                    sys.stdout.write("failed\n")
                    if show_traceback:
                        traceback.print_exc()
                    raise MigrationError()
                else:
                    sys.stdout.write("success\n")
        
        Migration.objects.using(database).create(
            migration_label=os.path.split(migration)[-1],
            content=content,
            scm_version=self._get_rev(migration),
        )
        
        return created_models
    
    def init_nashvegas(self):
        # Copied from line 35 of django.core.management.commands.syncdb
        # Import the 'management' module within each installed app, to register
        # dispatcher events.
        for app_name in settings.INSTALLED_APPS:
            try:
                import_module(".management", app_name)
            except ImportError, exc:
                # This is slightly hackish. We want to ignore ImportErrors
                # if the "management" module itself is missing -- but we don't
                # want to ignore the exception if the management module exists
                # but raises an ImportError for some reason. The only way we
                # can do this is to check the text of the exception. Note that
                # we're a bit broad in how we check the text, because different
                # Python implementations may not use the same text.
                # CPython uses the text "No module named management"
                # PyPy uses "No module named myproject.myapp.management"
                msg = exc.args[0]
                if not msg.startswith("No module named") or "management" not in msg:
                    raise
        
        # @@@ make cleaner / check explicitly for model instead of looping over and doing string comparisons
        databases = self.databases or get_capable_databases()
        for database in databases:
            connection = connections[database]
            cursor = connection.cursor()
            all_new = get_sql_for_new_models(['nashvegas'], using=database)
            for lines in all_new:
                to_execute = "\n".join(
                    [l for l in lines.split("\n") if not l.startswith("### New Model: ")]
                )
                if not to_execute:
                    continue
                cursor.execute(to_execute)
                transaction.commit_unless_managed(using=database)
    
    def create_all_migrations(self):
        for database in get_capable_databases():
            statements = get_sql_for_new_models(using=database)
            if len(statements) == 0:
                continue
            
            number = self._get_current_migration_number(database)
            
            db_path = os.path.join(self.path, database)
            if not os.path.exists(db_path):
                os.makedirs(db_path)
            
            path = os.path.join(db_path, '%s.sql' % (str(number + 1).zfill(4),))
            if os.path.exists(path):
                raise CommandError("Unable to create %r: File already exists" % path)
            
            with open(path, 'w') as fp:
                for s in statements:
                    fp.write(s + '\n')
            
            print "Created new migration: %r" % path
    
    def create_migrations(self, database):
        statements = get_sql_for_new_models(self.args, using=database)
        if len(statements) > 0:
            for s in statements:
                print s
    
    def execute_migrations(self, show_traceback=True):
        """
        Executes all pending migrations across all capable
        databases
        """
        all_migrations = get_pending_migrations(self.path, self.databases)
        
        if not len(all_migrations):
            sys.stdout.write("There are no migrations to apply.\n")
        
        for db, migrations in all_migrations.iteritems():
            connection = connections[db]
            
            # init connection
            cursor = connection.cursor()
            cursor.close()
                        
            for migration in migrations:
                migration_path = self._get_migration_path(db, migration)
                
                with Transactional():
                    sys.stdout.write("Executing migration %r on %r...." % (migration, db))
                    created_models = self._execute_migration(db, migration_path, show_traceback=show_traceback)

                    emit_post_sync_signal(
                        created_models=created_models,
                        verbosity=self.verbosity,
                        interactive=self.interactive,
                        db=db,
                    )
            
            sys.stdout.write("Running loaddata for initial_data fixtures on %r.\n" % db)
            call_command(
                "loaddata",
                "initial_data",
                verbosity=self.verbosity,
                database=db,
            )
    
    def seed_migrations(self, stop_at=None):
        # @@@ the command-line interface needs to be re-thinked
        # TODO: this needs to be able to handle multi-db when you're specifying stop_at
        if stop_at is None and self.args:
            stop_at = self.args[0]
        
        if stop_at:
            try:
                stop_at = int(stop_at)
            except ValueError:
                raise CommandError("Invalid --seed migration")
            except IndexError:
                raise CommandError("Usage: ./manage.py upgradedb --seed [stop_at]")

        all_migrations = get_pending_migrations(self.path, self.databases, stop_at=stop_at)
        for db, migrations in all_migrations.iteritems():
            for migration in migrations:
                migration_path = self._get_migration_path(db, migration)

                m, created = Migration.objects.using(db).get_or_create(
                    migration_label=os.path.split(migration)[-1],
                    content=open(migration_path, "rb").read()
                )
                if created:
                    # this might have been executed prior to committing
                    m.scm_version = self._get_rev(migration)
                    m.save()
                    print "%s:%s has been seeded" % (db, m.migration_label)
                else:
                    print "%s:%s was already applied" % (db, m.migration_label)
    
    def list_migrations(self):
        all_migrations = get_pending_migrations(self.path, self.databases)
        if len(all_migrations) == 0:
            print "There are no migrations to apply."
            return
        
        print "Migrations to Apply:"
        for database, migrations in all_migrations.iteritems():
            for script in migrations:
                print "\t%s: %s" % (database, script)
    
    def _get_default_migration_path(self):
        try:
            path = os.path.dirname(os.path.normpath(os.sys.modules[settings.SETTINGS_MODULE].__file__))
        except KeyError:
            path = os.getcwd()
        return os.path.join(path, "migrations")

    def handle(self, *args, **options):
        """
        Upgrades the database.
        
        Executes SQL scripts that haven't already been applied to the
        database.
        """
        self.do_list = options.get("do_list")
        self.do_execute = options.get("do_execute")
        self.do_create = options.get("do_create")
        self.do_create_all = options.get("do_create_all")
        self.do_seed = options.get("do_seed")
        self.args = args
        
        if options.get("path"):
            self.path = options.get("path")
        else:
            default_path = self._get_default_migration_path()
            self.path = getattr(settings, "NASHVEGAS_MIGRATIONS_DIRECTORY", default_path)
        
        self.verbosity = int(options.get("verbosity", 1))
        self.interactive = options.get("interactive")
        self.databases = options.get("databases")
        
        # We only use the default alias in creation scenarios (upgrades default to all databases)
        if self.do_create and not self.databases:
            self.databases = [DEFAULT_DB_ALIAS]
        
        if self.do_create and self.do_create_all:
            raise CommandError("You cannot combine --create and --create-all")
        
        self.init_nashvegas()
        
        if self.do_create_all:
            self.create_all_migrations()
        elif self.do_create:
            self.create_migrations(self.databases)
        
        if self.do_execute:
            self.execute_migrations()
        
        if self.do_list:
            self.list_migrations()
        
        if self.do_seed:
            self.seed_migrations()
