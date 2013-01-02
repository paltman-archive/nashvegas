import difflib

from optparse import make_option
from subprocess import PIPE, Popen

from django.db import connections, DEFAULT_DB_ALIAS
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


NASHVEGAS = getattr(settings, "NASHVEGAS", {})


def ignorable_sql(line, level):
    if level == 0:
        return False  # ignore nothing

    # level 1 = ignore comments
    if level > 0 and line.lstrip().startswith("--"):
        return True

    # level 2 = ignore constraints
    if level > 1 and line.lstrip().lower().startswith("add constraint"):
        return True

    return False


def normalize_sql(lines, level=1):
    """ perform simple normalization: remove comments """
    return [line for line in lines if not ignorable_sql(line, level)]


class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option("-n", "--name",
                    action="store",
                    dest="db_name",
                    help="The name of the database to hold the truth schema"
                         " (defaults to <name>_compare"),
        make_option("-d", "--database",
                    action="store",
                    dest="database",
                    default=DEFAULT_DB_ALIAS,
                    help="Nominates a database to synchronize. "
                         "Defaults to the \"default\" database."),
        make_option("-l", "--lines-of-context",
                    action="store",
                    dest="lines",
                    default=10,
                    help="Show this amount of context (default 10)."),
        make_option("-i", "--ignore-level",
                    action="store",
                    dest="ignore",
                    default=1,
                    help="Ignore level. 0=ignore nothing, 1=ignore comments (default), "
                         "2=ignore constraints"),
    )
    help = "Checks for schema differences."
    
    def setup_database(self):
        command = NASHVEGAS.get("createdb", "createdb {dbname}")
        Popen(command.format(dbname=self.compare_name), shell=True).wait()
    
    def teardown_database(self):
        command = NASHVEGAS.get("dropdb", "dropdb {dbname}")
        Popen(command.format(dbname=self.compare_name), shell=True).wait()
    
    def handle(self, *args, **options):
        """
        Compares current database with a migrations.
        
        Creates a temporary database, applies all the migrations to it, and
        then dumps the schema from both current and temporary, diffs them,
        then report the diffs to the user.
        """
        self.db = options.get("database", DEFAULT_DB_ALIAS)
        self.current_name = connections[self.db].settings_dict["NAME"]
        self.compare_name = options.get("db_name")
        self.lines = options.get("lines")
        self.ignore = int(options.get('ignore'))

        if not self.compare_name:
            self.compare_name = "%s_compare" % self.current_name
        
        command = NASHVEGAS.get("dumpdb", "pg_dump -s {dbname}")
        
        print "Getting schema for current database..."
        current_sql = Popen(
            command.format(dbname=self.current_name),
            shell=True,
            stdout=PIPE
        ).stdout.readlines()
        
        print "Getting schema for fresh database..."
        self.setup_database()
        connections[self.db].close()
        connections[self.db].settings_dict["NAME"] = self.compare_name
        try:
            call_command("syncdb", interactive=False, verbosity=0, migrations=False)
            new_sql = Popen(
                command.format(dbname=self.compare_name).split(),
                stdout=PIPE
            ).stdout.readlines()
        finally:
            connections[self.db].close()
            connections[self.db].settings_dict["NAME"] = self.current_name
            self.teardown_database()
        
        print "Outputing diff between the two..."
        print "".join(difflib.unified_diff(normalize_sql(current_sql, self.ignore),
                                           normalize_sql(new_sql, self.ignore),
                                           n=int(self.lines)))
