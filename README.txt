=========
Nashvegas
=========

The purpose of this app is to enable a plug and play method for managing database changes.

It really just abstracting out into a reusable app, a script that I have been using in a 
four person development team quite successfully for more than 6 months now.  

Database migrations is a large topic with a lot of different approaches.  This approach 
worked well for my needs so I thought I'd put it out on the "Interwebs" and let the 
community judge it for it's usefulness.

How to Use
----------

* Add the application to your PYTHON_PATH
* Add the application to your INSTALLED_APPS list in your settings.py file.
* Execute the command line:

    $ ./manage.py upgradedb --list|--execute [--path /path/to/scripts]

Options
-------

* --list - Lists all the scripts that will need to be executed.
* --execute - Executes all the scripts that need to be executed.
* --path - The fully qualified path to the where the database scripts are located.
           This defaults to {{ PROJECT_PATH }}/db

Conventions
-----------

Part of the simplicity of this solution is based on the naming conventions of the sql
scripts.  They should be named:

    YYYYMMDD-##.sql

Where YYYY is the 4 digit year, MM is the two digit month, and DD is the two digit day.

A tabled called `versions` will be created in your database the first time this command
executes.  The rows in this table track which scripts have been executed.  You should 
rarely if ever need to examine this table, or even be aware of its existence.
