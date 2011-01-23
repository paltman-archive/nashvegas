from django.core.management.color import no_style
from django.core.management.sql import custom_sql_for_model
from django.db import connections, router, models, DEFAULT_DB_ALIAS
from django.utils.datastructures import SortedDict


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
        db_table_in = (converter(opts.db_table) in tables)
        auto_create_in = (
            opts.auto_created and \
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
