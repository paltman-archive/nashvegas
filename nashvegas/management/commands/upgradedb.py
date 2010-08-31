import os
import sys

from optparse import make_option
from subprocess import Popen, PIPE, STDOUT

from django.db import connections, transaction, DEFAULT_DB_ALIAS
from django.db.models import get_model
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.management.sql import emit_post_sync_signal

from nashvegas.models import Migration
from nashvegas.utils import get_sql_for_new_models, get_db_exec_args


sys.path.append("migrations")


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

    def _filter_down(self):
        
        applied = []
        to_execute = []
        scripts_in_directory = []
        
        try:
            already_applied = Migration.objects.all().order_by("migration_label")
            
            for x in already_applied:
                applied.append(x.migration_label)
            
            in_directory = os.listdir(self.path)
            in_directory.sort()
            applied.sort()
            
            for script in in_directory:
                if os.path.splitext(script)[-1] in [".sql", ".py"]:
                    scripts_in_directory.append(script)
            
            for script in scripts_in_directory:
                if script not in applied:
                    to_execute.append(script)
        except OSError, e:
            print str(e)

        return to_execute

    def _get_rev(self, fpath):
        """Get an SCM verion number.  Try svn and git."""
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
            print "BEGIN;"
            for s in statements:
                print s
    
    def execute_migrations(self):
        migrations = self._filter_down()
        if len(migrations) == 0:
            print "There are no migrations to apply."
            return
        
        created_models = []
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
                
                p = Popen(
                    get_db_exec_args(self.db),
                    stdin=PIPE,
                    stdout=PIPE,
                    stderr=STDOUT
                )
                
                (out, err) = p.communicate(input=to_execute)
                print "stdout:", out
                print "stderr:", err
                
                if p.returncode != 0:
                    sys.exit(
                        "\nExecution stopped!\n\nThere was an error in %s\n" % \
                            migration_path
                    )
                
                created_models.extend([
                    get_model(
                        *l.replace("### New Model: ", "").strip().split(".")
                    ) 
                    for l in lines if l.startswith("### New Model: ")
                ])
            elif migration_path.endswith(".py"):
                module = __import__("%s" % os.path.splitext(migration)[0])
                if hasattr(module, 'migrate') and callable(module.migrate):
                    module.migrate()
            
            Migration.objects.create(
                migration_label=migration,
                content=content,
                scm_version=self._get_rev(migration_path)
            )
            fp.close()
        
        emit_post_sync_signal(
            created_models,
            self.verbosity,
            self.interactive,
            self.db
        )
        
        call_command(
            'loaddata',
            'initial_data',
            verbosity=self.verbosity,
            database=self.db
        )
    
    def seed_migrations(self):
        migrations = [os.path.join(self.path, m) for m in self._filter_down()]
        if len(self.args) > 0:
            migrations = [arg for arg in self.args if not arg.endswith(".pyc")]
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
        self.verbosity = int(options.get('verbosity', 1))
        self.interactive = options.get('interactive')
        self.db = options.get('database', DEFAULT_DB_ALIAS)
        
        self.init_nashvegas()

        if self.do_create:
            self.create_migrations()
        
        if self.do_execute:
            self.execute_migrations()
        
        if self.do_list:
            self.list_migrations()
        
        if self.do_seed:
            self.seed_migrations()

