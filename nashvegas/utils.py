import itertools
import os.path
import re

from collections import defaultdict
from django.core.management.color import no_style
from django.core.management.sql import custom_sql_for_model
from django.db import connections, router, models, DEFAULT_DB_ALIAS
from django.utils.datastructures import SortedDict
from nashvegas.exceptions import MigrationError
from nashvegas.models import Migration

MIGRATION_NAME_RE = re.compile(r"(\d+)(.*)")


def get_sql_for_new_models(apps=None, using=DEFAULT_DB_ALIAS):
    """
    Unashamedly copied and tweaked from django.core.management.commands.syncdb
    """
    connection = connections[using]
    
    # Get a list of already installed *models* so that references work right.
    tables = connection.introspection.table_names()
    seen_models = connection.introspection.installed_models(tables)
    created_models = set()
    pending_references = {}
    
    if apps:
        apps = [models.get_app(a) for a in apps]
    else:
        apps = models.get_apps()
    
    # Build the manifest of apps and models that are to be synchronized
    all_models = [
        (app.__name__.split('.')[-2], [
            m
            for m in models.get_models(app, include_auto_created=True)
            if router.allow_syncdb(using, m)
        ])
        for app in apps
    ]
    
    def model_installed(model):
        opts = model._meta
        converter = connection.introspection.table_name_converter
        db_table_in = (converter(opts.db_table) in tables)
        auto_create_in = (
            opts.auto_created and
            converter(opts.auto_created._meta.db_table) in tables
        )
        return not (db_table_in or auto_create_in)
    
    manifest = SortedDict(
        (app_name, filter(model_installed, model_list))
        for app_name, model_list in all_models
    )
    
    statements = []
    sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            # Create the model's database table, if it doesn't already exist.
            sql, references = connection.creation.sql_create_model(
                model,
                no_style(),
                seen_models
            )
            
            seen_models.add(model)
            created_models.add(model)
            statements.append("### New Model: %s.%s" % (
                app_name,
                str(model).replace("'>", "").split(".")[-1]
            ))
            
            for refto, refs in references.items():
                pending_references.setdefault(refto, []).extend(refs)
                if refto in seen_models:
                    sql.extend(
                        connection.creation.sql_for_pending_references(
                            refto,
                            no_style(),
                            pending_references
                        )
                    )
            
            sql.extend(
                connection.creation.sql_for_pending_references(
                    model,
                    no_style(),
                    pending_references
                )
            )
            statements.extend(sql)
    
    custom_sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            if model in created_models:
                custom_sql = custom_sql_for_model(
                    model,
                    no_style(),
                    connection
                )
                
                if custom_sql:
                    statements.extend(custom_sql)
    
    index_sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            if model in created_models:
                index_sql = connection.creation.sql_indexes_for_model(
                    model,
                    no_style()
                )
                
                if index_sql:
                    statements.extend(index_sql)
    
    return statements


def get_capable_databases():
    """
    Returns a list of databases which are capable of supporting
    Nashvegas (based on their routing configuration).
    """
    for database in connections:
        if router.allow_syncdb(database, Migration):
            yield database


def get_file_list(path, max_depth=1, cur_depth=0):
    """
    Recursively returns a list of all files up to ``max_depth``
    in a directory.
    """
    if os.path.exists(path):
        for name in os.listdir(path):
            if name.startswith('.'):
                continue

            full_path = os.path.join(path, name)
            if os.path.isdir(full_path):
                if cur_depth == max_depth:
                    continue

                for result in get_file_list(full_path, max_depth, cur_depth + 1):
                    yield result

            else:
                yield full_path


def get_applied_migrations(databases=None):
    """
    Returns a dictionary containing lists of all applied migrations
    where the key is the database alias.
    """
    if not databases:
        databases = get_capable_databases()
    else:
        # We only loop through databases that are listed as "capable"
        all_databases = list(get_capable_databases())
        databases = list(itertools.ifilter(lambda x: x in all_databases, databases))

    results = defaultdict(list)
    for db in databases:
        for x in Migration.objects.using(db).order_by("migration_label"):
            results[db].append(x.migration_label)

    return results


def get_all_migrations(path, databases=None):
    """
    Returns a dictionary of database => [migrations] representing all
    migrations contained in ``path``.
    """
    # database: [(number, full_path)]
    possible_migrations = defaultdict(list)

    try:
        in_directory = sorted(get_file_list(path))
    except OSError:
        import traceback
        print "An error occurred while reading migrations from %r:" % path
        traceback.print_exc()
        return {}

    # Iterate through our results and discover which migrations are actually runnable
    for full_path in in_directory:
        child_path, script = os.path.split(full_path)
        name, ext = os.path.splitext(script)

        # the database component is default if this is in the root directory
        # is <directory> if in a subdirectory
        if path == child_path:
            db = DEFAULT_DB_ALIAS
        else:
            db = os.path.split(child_path)[-1]

        # filter by database if set
        if databases and db not in databases:
            continue

        match = MIGRATION_NAME_RE.match(name)
        if match is None:
            raise MigrationError("Invalid migration file prefix %r "
                                 "(must begin with a number)" % name)

        number = int(match.group(1))
        if ext in [".sql", ".py"]:
            possible_migrations[db].append((number, full_path))

    return possible_migrations


def get_pending_migrations(path, databases=None, stop_at=None):
    """
    Returns a dictionary of database => [migrations] representing all pending
    migrations.
    """
    if stop_at is None:
        stop_at = float("inf")

    # database: [(number, full_path)]
    possible_migrations = get_all_migrations(path, databases)
    # database: [full_path]
    applied_migrations = get_applied_migrations(databases)
    # database: [full_path]
    to_execute = defaultdict(list)

    for database, scripts in possible_migrations.iteritems():
        applied = applied_migrations[database]
        pending = to_execute[database]
        for number, migration in scripts:
            path, script = os.path.split(migration)
            if script not in applied and number <= stop_at:
                pending.append(script)

    return dict((k, v) for k, v in to_execute.iteritems() if v)
