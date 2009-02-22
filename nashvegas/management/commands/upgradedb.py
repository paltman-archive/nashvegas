"""
Execute SQL Scripts / Upgrade Database
======================================

"""
import os
from django.conf import settings
from django.db import connection
from django.core.management.base import BaseCommand, CommandError


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

        def handle(self, *args, **options):
            """
            Upgrades the database.

            Executes SQL scripts that haven't already been applied to the 
            database.
            """
            self.list_todo = options.get('list_todo')
            self.execute_todo = options.get('execute_todo')
            self.path = options.get('path')


