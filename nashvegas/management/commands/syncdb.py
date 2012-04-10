from django.core.management import call_command
from django.core.management.commands.syncdb import Command as SyncDBCommand


class Command(SyncDBCommand):
    def handle_noargs(self, **options):
        call_command("upgradedb", do_execute=True)
