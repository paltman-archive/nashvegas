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
        make_option("-n", "--name", action = "store", dest = "db_name",
                    default = "%s_compare" % connections.databases[DEFAULT_DB_ALIAS]["NAME"],
                    help = "The name of the database to hold the truth schema"),
    )
    help = "Compares current database with the one that nashvegas will build from scratch."

    def setup_database(self):
        command = "createdb %s" % self.name
        if NASHVEGAS and "createdb" in settings.NASHVEGAS:
            command = settings.NASHVEGAS["createdb"]
        Popen(command.split()).wait()

    def teardown_database(self):
        command = "dropdb %s" % self.name
        if NASHVEGAS and "dropdb" in settings.NASHVEGAS:
            command = settings.NASHVEGAS["dropdb"]
        Popen(command.split()).wait()

    def handle(self, *args, **options):
        """
        Compares current database with a migrations.

        Creates a temporary database, applies all the migrations to it, and then
        dumps the schema from both current and temporary, diffs them, then
        report the diffs to the user.
        """
        self.name = options.get("db_name")
        command = "pg_dump -s %s" % connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        if NASHVEGAS and "pg_dump" in settings.NASHVEGAS:
            command = settings.NASHVEGAS["pg_dump"]

        print "Getting schema for current database..."
        current_sql = Popen(command.split(), stdout=PIPE).stdout.readlines()

        print "Getting schema for fresh database..."
        self.setup_database()
        orig = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        connections[DEFAULT_DB_ALIAS].close()
        connections[DEFAULT_DB_ALIAS].settings_dict["NAME"] = self.name
        call_command("syncdb", interactive=False, verbosity=0)
        new_sql = Popen(command.split(), stdout=PIPE).stdout.readlines()
        connections[DEFAULT_DB_ALIAS].close()
        connections[DEFAULT_DB_ALIAS].settings_dict["NAME"] = orig
        self.teardown_database()

        print "Outputing diff between the two..."
        print "".join(difflib.unified_diff(current_sql, new_sql))
