from django.core.management.color import no_style
from django.core.management.sql import custom_sql_for_model
from django.db import connections, router, models, DEFAULT_DB_ALIAS
from django.utils.datastructures import SortedDict


def _get_postgresql_args(connection, settings_dict):
    args = [connection.client.executable_name]
    if settings_dict['USER']:
        args += ["-U", settings_dict['USER']]
    if settings_dict['HOST']:
        args.extend(["-h", settings_dict['HOST']])
    if settings_dict['PORT']:
        args.extend(["-p", str(settings_dict['PORT'])])
    args += [settings_dict['NAME']]
    args.extend(["--set", "ON_ERROR_STOP=TRUE"])
    return args


def _get_sqlite_args(connection, settings_dict):
    args = [connection.client.executable_name, settings_dict["NAME"]]
    return args


def _get_mysql_args(connection, settings_dict):
    args = [connection.client.executable_name]
    db = settings_dict['OPTIONS'].get('db', settings_dict['NAME'])
    user = settings_dict['OPTIONS'].get('user', settings_dict['USER'])
    passwd = settings_dict['OPTIONS'].get('passwd', settings_dict['PASSWORD'])
    host = settings_dict['OPTIONS'].get('host', settings_dict['HOST'])
    port = settings_dict['OPTIONS'].get('port', settings_dict['PORT'])
    defaults_file = settings_dict['OPTIONS'].get('read_default_file')
    # Seems to be no good way to set sql_mode with CLI.

    if defaults_file:
        args += ["--defaults-file=%s" % defaults_file]
    if user:
        args += ["--user=%s" % user]
    if passwd:
        args += ["--password=%s" % passwd]
    if host:
        args += ["--host=%s" % host]
    if port:
        args += ["--port=%s" % port]
    if db:
        args += [db]
    return args


def _get_oracle_args(connection, settings_dict):
    args = [
        connection.client.executable_name,
        "-L",
        connection._connect_string()
    ]
    return args


GET_ARGS_REGISTRY = {
    "django.db.backends.mysql": _get_mysql_args,
    "django.db.backends.oracle": _get_oracle_args,
    "django.db.backends.postgresql_psycopg2": _get_postgresql_args,
    "django.db.backends.postgresql": _get_postgresql_args,
    "django.db.backends.sqlite3": _get_sqlite_args
}


def get_db_exec_args(db):
    """
    Pulled out of django.db.backends.*.client.DatabaseClient
    """
    connection = connections[db]
    settings_dict = connection.settings_dict
    get_args_func = GET_ARGS_REGISTRY.get(settings_dict["ENGINE"], None)
    if get_args_func is not None:
        return get_args_func(connection, settings_dict)


def get_sql_for_new_models():
    """
    Unashamedly copied and tweaked from djang.core.management.commands.syncdb
    """
    connection = connections[DEFAULT_DB_ALIAS]
    
    # Get a list of already installed *models* so that references work right.
    tables = connection.introspection.table_names()
    seen_models = connection.introspection.installed_models(tables)
    created_models = set()
    pending_references = {}

    # Build the manifest of apps and models that are to be synchronized
    all_models = [
        (app.__name__.split('.')[-2],
            [m for m in models.get_models(app, include_auto_created=True)
            if router.allow_syncdb(DEFAULT_DB_ALIAS, m)])
        for app in models.get_apps()
    ]
    def model_installed(model):
        opts = model._meta
        converter = connection.introspection.table_name_converter
        return not ((converter(opts.db_table) in tables) or
            (opts.auto_created and converter(opts.auto_created._meta.db_table) in tables))
    
    manifest = SortedDict(
        (app_name, filter(model_installed, model_list))
        for app_name, model_list in all_models
    )
    
    statements = []
    sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            # Create the model's database table, if it doesn't already exist.
            sql, references = connection.creation.sql_create_model(model, no_style(), seen_models)
            seen_models.add(model)
            created_models.add(model)
            statements.append("### New Model: %s.%s" % (app_name, str(model).replace("'>", "").split(".")[-1]))
            for refto, refs in references.items():
                pending_references.setdefault(refto, []).extend(refs)
                if refto in seen_models:
                    sql.extend(connection.creation.sql_for_pending_references(refto, no_style(), pending_references))
            sql.extend(connection.creation.sql_for_pending_references(model, no_style(), pending_references))
            statements.extend(sql)
    if sql:
        statements.append("COMMIT;")
    
    custom_sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            if model in created_models:
                custom_sql = custom_sql_for_model(model, no_style(), connection)
                if custom_sql:
                    statements.extend(custom_sql)
    
    if custom_sql:
        statements.append("COMMIT;")
    
    index_sql = None
    for app_name, model_list in manifest.items():
        for model in model_list:
            if model in created_models:
                index_sql = connection.creation.sql_indexes_for_model(model, no_style())
                if index_sql:
                    statements.extend(index_sql)
    
    if index_sql:
        statements.append("COMMIT;")
    
    return statements