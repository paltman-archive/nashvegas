import os

from optparse import make_option

from django.db import connections, transaction, DEFAULT_DB_ALIAS
from django.conf import settings
from django.core.management.base import BaseCommand

from nashvegas.models import Migration
from nashvegas.utils import get_sql_for_new_models


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
            make_option("-l", "--list", action = "store_true",
                        dest = "do_list", default = True,
                        help = "Enumerate the list of migrations to execute."),
            make_option("-e", "--execute", action = "store_true",
                        dest = "do_execute", default = False,
                        help = "Execute migrations not in versions table."),
            make_option("-c", "--create", action = "store_true",
                        dest = "do_create", default = True,
                        help = "Generates sql for models that are installed but not in your database."),
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
            
            print "# ALREADY APPLIED:"
            for x in already_applied:
                applied.append(x.migration_label)
                print "#\t%s\tr%s" % (x.migration_label, x.date_created)
            
            in_directory = os.listdir(self.path)
            in_directory.sort()
            applied.sort()
            
            for script in in_directory:
                if os.path.splitext(script)[-1] in [".sql", ".py"]:
                    scripts_in_directory.append(script)
            
            for script in scripts_in_directory:
                if script not in applied:
                    to_execute.append(script)
            
            print "# TO EXECUTE:"
            for script in to_execute:
                print "#\t%s" % script
        except OSError, e:
            print str(e)

        return to_execute

    # def _get_rev(self, fpath):
    #     """Get an SCM verion number.  Try svn and git."""
    #     rev = None
    #     try:
    #         cmd = ["git", "log", "-n1", "--pretty=format:"%h"", sql]
    #         rev = Popen(cmd, stdout=PIPE).communicate()[0]
    #     except:
    #         pass
    # 
    #     if not rev:
    #         try:
    #             cmd = ["svn", "info", sql]
    #             svninfo = Popen(cmd, stdout=PIPE).stdout.readlines()
    #             for info in svninfo:
    #                 tokens = info.split(":")
    #                 if tokens[0].strip() == "Last Changed Rev":
    #                     rev = tokens[1].strip()
    #         except:
    #             pass
    # 
    #     return rev
    
    def init_nashvegas(self):
        # @@@ make cleaner / check explicitly for model instead of looping over and doing string comparisons
        connection = connections[DEFAULT_DB_ALIAS]
        cursor = connection.cursor()
        all_new = get_sql_for_new_models()
        for s in all_new:
            if "nashvegas_migration" in s:
                cursor.execute(s)
                transaction.commit_unless_managed(using=DEFAULT_DB_ALIAS)
                return
    
    def create_migrations(self):
        for s in get_sql_for_new_models():
            print s
    
    def execute_migrations(self):
        # @@@ Loop over _filter_down results
        # @@@ Execute entire files at once (simulate ./manage.py dbshell < SCRIPT)
        # @@@ Detect if CREATE TABLE exists in migrations and fire signals et al (simulating syncdb)
        # @@@ Create contenttype records and permissions ? (simulating syncdb)
        pass
    
    def list_migrations(self):
        pass
    
    def handle(self, *args, **options):
        """
        Upgrades the database.

        Executes SQL scripts that haven't already been applied to the
        database.
        """
        self.do_list = options.get("do_list")
        self.do_execute = options.get("do_execute")
        self.do_create = options.get("do_create")
        self.path = options.get("path")
        
        self.init_nashvegas()

        if self.do_create:
            self.create_migrations()
        
        if self.do_execute:
            self.execute_migrations()
        
        if self.do_list:
            self.list_migrations()
        
