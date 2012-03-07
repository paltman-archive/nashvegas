import difflib

from optparse import make_option
from subprocess import PIPE, Popen

from django.db import connections, DEFAULT_DB_ALIAS
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


NASHVEGAS = getattr(settings, "NASHVEGAS", None)


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option("-n", "--name", action="store", dest="db_name",
                    help="The name of the database to hold the truth schema (defaults to <name>_compare"),
        make_option("-d", "--database", action="store", dest="database",
                    default=DEFAULT_DB_ALIAS, help="Nominates a database to synchronize. "
                    "Defaults to the \"default\" database."),
    )
    help = "Compares current database with the one that nashvegas will build from scratch."
    
    def setup_database(self):
        command = "createdb %s" % self.compare_name
        if NASHVEGAS and "createdb" in settings.NASHVEGAS:
            command = "%s %s" % (settings.NASHVEGAS["createdb"], self.compare_name)
        Popen(command.split()).wait()
    
    def teardown_database(self):
        command = "dropdb %s" % self.compare_name
        if NASHVEGAS and "dropdb" in settings.NASHVEGAS:
            command = "%s %s" % (settings.NASHVEGAS["dropdb"], self.compare_name)
        Popen(command.split()).wait()
    
    def handle(self, *args, **options):
        """
        Compares current database with a migrations.
        
        Creates a temporary database, applies all the migrations to it, and then
        dumps the schema from both current and temporary, diffs them, then
        report the diffs to the user.
        """
        self.db = options.get("database", DEFAULT_DB_ALIAS)
        self.current_name = connections[self.db].settings_dict["NAME"]
        self.compare_name = options.get("db_name")
        if not self.compare_name:
            self.compare_name = "%s_compare" % self.current_name

        command = "pg_dump -s"
        if NASHVEGAS and "pg_dump" in settings.NASHVEGAS:
            command = settings.NASHVEGAS["pg_dump"] 
        
        print "Getting schema for current database..."
        current_sql = Popen(command.split() + [self.current_name], 
            stdout=PIPE).stdout.readlines()
        
        print "Getting schema for fresh database..."
        self.setup_database()
        connections[self.db].close()
        connections[self.db].settings_dict["NAME"] = self.compare_name
        call_command("syncdb", interactive=False, verbosity=0)
        new_sql = Popen(command.split() + [self.compare_name], 
            stdout=PIPE).stdout.readlines()
        connections[self.db].close()
        connections[self.db].settings_dict["NAME"] = self.current_name
        self.teardown_database()
        
        print "Outputing diff between the two..."
        print "".join(difflib.unified_diff(current_sql, new_sql))
