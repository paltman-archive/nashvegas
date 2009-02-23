"""
Execute SQL Scripts / Upgrade Database
======================================

"""
import re
import os
import hashlib
from django.conf import settings
from django.db import connection
from django.core.management.base import BaseCommand, CommandError
from optparse import make_option


reSQL = re.compile(";\s*$", re.MULTILINE)

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
            make_option('-l','--list', action='store_true',
                        dest='list_todo', default=True,
                        help='Enumerate the list of scripts to execute.'),
            make_option('-e', '--execute', action='store_true',
                        dest='execute_todo', default=False,
                        help='Execute scripts not in versions table.'),
            make_option('-p','--path', dest='path', 
                default=os.path.join(settings.PROJECT_PATH, 'db'), 
                help="The path to the database scripts.")
        )
    help = "Upgrade database."
        
    def _versions_create(self):
        """Creates the versions table if it doesn't already exist."""
        tables = connection.introspection.table_names()
        if 'versions' not in tables:
            sql = """CREATE TABLE `versions` (
                `version` VARCHAR(200) NOT NULL, 
                `date_created` DATETIME NOT NULL,
                `sql_executed` LONGTEXT NULL,
                `scm_version` int null
            );"""
            cursor = connection.cursor()
            cursor.execute(sql)
            cursor.close()
            print 'Versions table created.'
            return True
        return False
    
    def _get_version_list(self):
        """Gets list of already installed database scripts."""
        cursor = connection.cursor()
        sql = """select distinct version, scm_version 
                   from versions order by version;"""
        count = cursor.execute(sql)
        versions = []
        if count > 0:
           versions = [version for version in cursor.fetchall()]
        cursor.close()
        return versions
    
    def _filter_down(self):
        to_execute = []
        try:
            already_applied = self._get_version_list()
            print "# ALREADY APPLIED:"
            for x in already_applied:
                print '#\t%s\tr%s' % (x[0], x[1])
            in_directory = os.listdir(self.path)
            in_directory.sort()
            sql_in_directory = []
            for sql in in_directory:
                if os.path.splitext(sql)[-1] == '.sql':
                    sql_in_directory.append(sql)
            to_execute = []
            for sql in sql_in_directory:
                if sql not in [info[0] for info in already_applied]:
                    to_execute.append(sql)
            print '# TO EXECUTE:'
            for x in to_execute:
                print '#\t%s' % x
        except OSError, e:
            print str(e)
            
        return to_execute
    
    def _get_rev(self, fpath):
        """Get an SCM verion number.  Try svn and git."""
        rev = None
        try:
            rev = Popen(["git", "log", "-n1", "--pretty=format:'%h'", sql], stdout=PIPE).communicate()[0]
        except:
            pass
        
        if not rev:
            try:
                svninfo = Popen(["svn", "info", sql], stdout=PIPE).stdout.readlines()
                for info in svninfo:
                    tokens = info.split(':')
                    if tokens[0].strip() == 'Last Changed Rev':
                        rev = tokens[1].strip()
            except:
                pass
            
        return rev
        
    def _split_file(self, sql):
        full_path = os.path.join(self.path, sql)
        contents = open(full_path, 'r').read()
        size = os.stat(full_path).st_size
        sha1 = hashlib.sha1(contents).hexdigest()
        rev = self._get_rev(full_path)
        print "## Processing %s, %s bytes, sha1 %s, rev %s" % (sql, size, sha1, rev)
        return {'statements':reSQL.split(contents), 'full_path':full_path, 'contents':contents, 'size':size, 'sha1':sha1, 'rev':rev}
    
    def handle(self, *args, **options):
        """
        Upgrades the database.
    
        Executes SQL scripts that haven't already been applied to the 
        database.
        """
        self.list_todo = options.get('list_todo')
        self.execute_todo = options.get('execute_todo')
        self.path = options.get('path')
        
        ## Does versions table exist?  If not, create it.
        self._versions_create()
        for sql in self._filter_down():
            print sql
