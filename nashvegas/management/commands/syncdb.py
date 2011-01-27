from django.core.management.commands.syncdb import Command as SyncDBCommand


class Command(SyncDBCommand):
    """
    A custom syncdb command that asks you for confirmation
    before syncing the database.
    """
    
    def handle_noargs(self, **options):
        if options.get("interactive"):
            confirm = raw_input("""
You have requested a database sync.
This CONFLICTS WITH NASHVEGAS.
Are you sure you want to do this?

Type 'yes' to continue, or 'no' to cancel: """)
        else:
            confirm = "yes"
        
        if confirm == "yes":
            super(Command, self).handle_noargs(**options)
        else:
            print "Sync cancelled."

