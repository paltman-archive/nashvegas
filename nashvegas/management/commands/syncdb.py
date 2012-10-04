from django.core.management import call_command
from django.core.management.commands.syncdb import Command as SyncDBCommand
from optparse import make_option


class Command(SyncDBCommand):
    option_list = SyncDBCommand.option_list + (
        make_option('--skip-migrations',
                    action='store_false',
                    dest='migrations',
                    default=True,
                    help='Skip nashvegas migrations, do traditional syncdb'),
    )

    def handle_noargs(self, **options):
        # Run migrations first
        if options.get("database"):
            databases = [options.get("database")]
        else:
            databases = None
        migrations = options.get('migrations')

        if migrations:
            call_command(
                "upgradedb",
                do_execute=True,
                databases=databases,
                interactive=options.get("interactive"),
                verbosity=options.get("verbosity"),
            )

        # Follow up with a syncdb on anything that wasnt included in migrations
        # (this catches things like test-only models)
        super(Command, self).handle_noargs(**options)
