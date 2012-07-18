from django.core.management import call_command
from django.core.management.commands.syncdb import Command as SyncDBCommand


class Command(SyncDBCommand):
    def handle_noargs(self, **options):
        # Run migrations first
        if options.get("database"):
            databases = [options.get("database")]
        else:
            databases = None
        
        call_command("upgradedb",
            do_execute=True,
            databases=databases,
            interactive=options.get("interactive"),
            verbosity=options.get("verbosity"),
        )
        
        # Follow up with a syncdb on anything that wasnt included in migrations
        # (this catches things like test-only models)
        super(Command, self).handle_noargs(**options)
