import os
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

from nashvegas.models import Migration
from nashvegas.utils import get_sql_for_new_models


sys.path.append("migrations")


class MigrationError(Exception):
    pass


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option("-l", "--list", action = "store_true",
                    dest = "do_list", default = False,
                    help = "Enumerate the list of migrations to execute."),
        make_option("-e", "--execute", action = "store_true",
                    dest = "do_execute", default = False,
                    help = "Execute migrations not in versions table."),
        make_option("-c", "--create", action = "store_true",
                    dest = "do_create", default = False,
                    help = "Generates sql for models that are installed but not in your database."),
        make_option("-s", "--seed", action = "store_true",
                    dest = "do_seed", default = False,
                    help = "Seed nashvegas with migrations that have previously been applied in another manner."),
        make_option("--database", action="store", dest="database",
                    default=DEFAULT_DB_ALIAS, help="Nominates a database to synchronize. "
            "Defaults to the \"default\" database."),
        make_option("-p", "--path", dest = "path",
            default = os.path.join(
                os.path.dirname(
                    os.path.normpath(
                        os.sys.modules[settings.SETTINGS_MODULE].__file__
                    )
                ), "migrations"
            ),
            help="The path to the database migration scripts."))
    help = "Upgrade database."

    def _filter_down(self, stop_at=None):
        
        if stop_at is None:
            stop_at = float("inf")
        
        applied = []
        to_execute = []
        scripts_in_directory = []
        
        try:
            already_applied = Migration.objects.all().order_by("migration_label")
            
            for x in already_applied:
                applied.append(x.migration_label)
            
            in_directory = os.listdir(self.path)
            in_directory = [migration for migration in in_directory if
                            not migration.startswith(".")]
            in_directory.sort()
            applied.sort()
            
            for script in in_directory:
                name, ext = os.path.splitext(script)
                try:
                    number = int(name.split("_")[0])
                except ValueError:
                    raise MigrationError("Invalid migration file prefix (must begin with a number)")
                if ext in [".sql", ".py"]:
                    scripts_in_directory.append((number, script))
            
            for number, script in scripts_in_directory:
                if script not in applied and number <= stop_at:
                    to_execute.append(script)
        except OSError, e:
            print str(e)

        return to_execute

    def _get_rev(self, fpath):
        """
        Get an SCM verion number. Try svn and git.
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
    
    def init_nashvegas(self):
        # @@@ make cleaner / check explicitly for model instead of looping over and doing string comparisons
        connection = connections[self.db]
        cursor = connection.cursor()
        all_new = get_sql_for_new_models()
        for s in all_new:
            if "nashvegas_migration" in s:
                cursor.execute(s)
                transaction.commit_unless_managed(using=self.db)
                return
    
    def create_migrations(self):
        statements = get_sql_for_new_models()
        if len(statements) > 0:
            for s in statements:
                print s
    
    @transaction.commit_manually
    def execute_migrations(self, show_traceback=False):
        migrations = self._filter_down()
        
        if not len(migrations):
            print "There are no migrations to apply."
            return
        
        created_models = []
        
        try:
            for migration in migrations:
                migration_path = os.path.join(self.path, migration)
                fp = open(migration_path, "rb")
                lines = fp.readlines()
                fp.close()
                content = "".join(lines)
                
                if migration_path.endswith(".sql"):
                    to_execute = "".join(
                        [l for l in lines if not l.startswith("### New Model: ")]
                    )
                    connection = connections[self.db]
                    cursor = connection.cursor()
                    
                    sys.stdout.write("Executing %s... " % migration)
                    
                    try:
                        cursor.execute(to_execute)
                    except Exception:
                        sys.stdout.write("failed\n")
                        if show_traceback:
                            traceback.print_exc()
                        raise MigrationError()
                    else:
                        sys.stdout.write("success\n")
                    
                    created_models.extend([
                        get_model(
                            *l.replace("### New Model: ", "").strip().split(".")
                        ) 
                        for l in lines if l.startswith("### New Model: ")
                    ])
                elif migration_path.endswith(".py"):
                    sys.stdout.write("Executing %s... " % migration)
                    
                    module = {}
                    execfile(migration_path, {}, module)
                    
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
                
                Migration.objects.create(
                    migration_label=migration,
                    content=content,
                    scm_version=self._get_rev(migration_path)
                )
        except Exception:
            transaction.rollback(using=self.db)
            sys.stdout.write("Rolled back all migrations\n")
            sys.exit(1)
        else:
            emit_post_sync_signal(
                created_models,
                self.verbosity,
                self.interactive,
                self.db
            )
            call_command(
                "loaddata",
                "initial_data",
                verbosity=self.verbosity,
                database=self.db
            )
            transaction.commit(using=self.db)
    
    def seed_migrations(self, stop_at=None):
        # @@@ the command-line interface needs to be re-thinked
        try:
            stop_at = int(self.args[0])
        except ValueError:
            raise CommandError("Invalid --seed migration")
        migrations = [os.path.join(self.path, m) for m in self._filter_down(stop_at=stop_at)]
        for migration in migrations:
            m, created = Migration.objects.get_or_create(
                migration_label=os.path.basename(migration),
                content=open(migration, "rb").read()
            )
            if created:
                # this might have been executed prior to committing
                m.scm_version = self._get_rev(migration)
                m.save()
                print m.migration_label, "has been seeded"
            else:
                print m.migration_label, "was already applied."
    
    
    def list_migrations(self):
        migrations = self._filter_down()
        if len(migrations) == 0:
            print "There are no migrations to apply."
            return
        
        print "Migrations to Apply:"
        for script in migrations:
            print "\t%s" % script
    
    def handle(self, *args, **options):
        """
        Upgrades the database.

        Executes SQL scripts that haven't already been applied to the
        database.
        """
        self.do_list = options.get("do_list")
        self.do_execute = options.get("do_execute")
        self.do_create = options.get("do_create")
        self.do_seed = options.get("do_seed")
        self.args = args
        
        self.path = options.get("path")
        self.verbosity = int(options.get("verbosity", 1))
        self.interactive = options.get("interactive")
        self.db = options.get("database", DEFAULT_DB_ALIAS)
        
        self.init_nashvegas()

        if self.do_create:
            self.create_migrations()
        
        if self.do_execute:
            self.execute_migrations(show_traceback=True)
        
        if self.do_list:
            self.list_migrations()
        
        if self.do_seed:
            self.seed_migrations()

