import difflib

from optparse import make_option
from subprocess import PIPE, Popen

from django.db import connections, DEFAULT_DB_ALIAS
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option("-n", "--name", action = "store", dest = "db_name",
                    default = "%s_compare" % connections.databases[DEFAULT_DB_ALIAS]["NAME"],
                    help = "The name of the database to hold the truth schema"),
    )
    help = "Compares current database with the one that nashvegas will build from scratch."
    
    def setup_database(self):
        Popen(["createdb", self.name]).wait()
    
    def teardown_database(self):
        Popen(["dropdb", self.name]).wait()
    
    def handle(self, *args, **options):
        """
        Compares current database with a migrations.

        Creates a temporary database, applies all the migrations to it, and then
        dumps the schema from both current and temporary, diffs them, then
        report the diffs to the user.
        """
        self.name = options.get("db_name")
        
        print "Getting schema for current database..."
        current_sql = Popen(["pg_dump", "-s", connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]], stdout=PIPE).stdout.readlines()
        
        print "Getting schema for fresh database..."
        self.setup_database()
        orig = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        connections[DEFAULT_DB_ALIAS].close()
        connections[DEFAULT_DB_ALIAS].settings_dict["NAME"] = self.name
        call_command("upgradedb", do_execute=True)
        new_sql = Popen(["pg_dump", "-s", self.name], stdout=PIPE).stdout.readlines()
        connections[DEFAULT_DB_ALIAS].close()
        connections[DEFAULT_DB_ALIAS].settings_dict["NAME"] = orig
        self.teardown_database()
        
        print "Outputing diff between the two..."
        
        print "".join(difflib.unified_diff(current_sql, new_sql))
