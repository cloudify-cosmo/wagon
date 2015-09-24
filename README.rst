Wagon
=====

A wagon (also spelt waggon in British and Commonwealth English) is a
heavy four-wheeled vehicle pulled by draught animals, used for
transporting goods, commodities, agricultural materials, supplies, and
sometimes people. Wagons are distinguished from carts, which have two
wheels, and from lighter four-wheeled vehicles primarily for carrying
people, such as carriages.

-  Master Branch |Build Status|
-  PyPI |PyPI|
-  Version |PypI|

Wagon creates tar.gz based archives containing sets of Python Wheels for
a single module with its dependencies and allows to install them.

(NOTE: Currently, only tested on Linux).

Cloudify Plugins are packaged as sets of Python
`Wheels <https://packaging.python.org/en/latest/distributing.html#wheels>`__
in tar.gz files and so we needed a tool to create such archives. Hence,
Wagon.

Installation
------------

.. code:: shell

    pip install wagon

Usage
-----

Create Packages
~~~~~~~~~~~~~~~

.. code:: shell

    wagon create --help

Examples
^^^^^^^^

.. code:: shell

    # create an archive by retrieving the source from PyPI and keep the downloaded wheels (kept under <cwd>/plugin)
    wagon create -s cloudify-script-plugin==1.2 --keep-wheels -v
    # create an archive package by retrieving the source from a URL and creates wheels from requirement files found within the archive.
    wagon create -s http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.tar.gz -r .
    # create an archive package by retrieving the source from a local path and output the tar.gz file to /tmp/<MODULE>.tar.gz (defaults to <cwd>/<MODULE>.tar.gz)
    wagon create -s ~/modules/cloudify-script-plugin/ -o /tmp/

The output package of the three commands should be something like
``cloudify_script_plugin-1.2-py27-none-any.tar.gz`` if running under
Python 2.7.x.

Install Packages
~~~~~~~~~~~~~~~~

.. code:: shell

    wagon install --help

Examples
^^^^^^^^

.. code:: shell

    # install a packaged module from a local package tar file and upgrade if already installed
    wagon install -s ~/tars/cloudify_script_plugin-1.2-py27-none-any.tar.gz --upgrade
    # install a packaged module from a url into an existing virtualenv
    wagon install -s http://me.com/cloudify_script_plugin-1.2-py27-none-any.tar.gz --virtualenv my_venv -v

Validate Packages
~~~~~~~~~~~~~~~~~

.. code:: sheel

    wagon validate --help

Examples
^^^^^^^^

.. code:: shell

    # validate that a package is a wagon compatible package
    wagon validate -s ~/tars/cloudify_script_plugin-1.2-py27-none-any.tar.gz
    # validate from a url
    wagon validate -s http://me.com/cloudify_script_plugin-1.2-py27-none-any.tar.gz

Naming and Versioning
---------------------

Source: PyPI
~~~~~~~~~~~~

When providing a PyPI source, it must be supplied as
MODULE\_NAME==MODULE\_VERSION. wagon then applies the correct name and
version to the archive according to the two parameters.

Source: Else
~~~~~~~~~~~~

For local path and URL sources, the name and version are automatically
extracted from the setup.py file.

NOTE: This means that when supplying a local path, you must supply a
path to the root of where your setup.py file resides.

NOTE: If using a URL, it must be a URL to a tar.gz file structured like
a GitHub tar.gz archive (e.g.
https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/master.tar.gz)

Metadata File and Wheels
------------------------

A Metadata file is generated for the archive and looks somewhat like
this:

::

    {
        "archive_name": "cloudify_script_plugin-1.2-py27-none-any.tar.gz",
        "build_server_os_properties": {
            "distribution": "ubuntu",
            "distribution_release": "trusty",
            "distribution_version": "14.04"
        },
        "module_name": "cloudify-script-plugin",
        "module_source": "cloudify-script-plugin==1.2",
        "module_version": "1.2",
        "supported_platform": "any",
        "wheels": [
            "proxy_tools-0.1.0-py2-none-any.whl",
            "bottle-0.12.7-py2-none-any.whl",
            "networkx-1.8.1-py2-none-any.whl",
            "pika-0.9.13-py2-none-any.whl",
            "cloudify_plugins_common-3.2.1-py2-none-any.whl",
            "requests-2.7.0-py2.py3-none-any.whl",
            "cloudify_rest_client-3.2.1-py2-none-any.whl",
            "cloudify_script_plugin-1.2-py2-none-any.whl"
        ]
    }

-  The wheels to be installed reside in the tar.gz file under
   'wheels/\*.whl'.
-  The Metadata file resides in the tar.gz file under 'module.json'.
-  The installer uses the metadata file to check that the platform fits
   the machine the module is being installed on.
-  The OS properties are specifically helpful to identify Linux
   distributions and their releases as compiled Wheels may vary between
   them.

Archive naming convention and Platform
--------------------------------------

The tar.gz archive is named according to the Wheel naming convention
described in
`PEP0427 <https://www.python.org/dev/peps/pep-0427/#file-name-convention>`__
aside from two fields:

Example: ``cloudify_fabric_plugin-1.2.1-py27-none-linux_x86_64.tar.gz``

-  ``{python tag}``: The Python version is set by the Python running the
   packaging process. That means that while a module might run on both
   py27 and py33 (for example), since the packaging process took place
   using Python 2.7, only py27 will be appended to the name. Note that
   we will be providing a way for the user to provide the supported
   Python versions explicitly.
-  ``{platform tag}``: The platform (e.g. ``linux_x86_64``, ``win32``)
   is set for a specific wheel. To know which platform the module can be
   installed on, all wheels are checked. If a specific wheel has a
   platform property other than ``any``, that platform will be used as
   the platform of the package. Of course, we assume that there can't be
   wheels downloaded or created on a specific machine platform that
   belongs to two different platforms.

.. |Build Status| image:: https://travis-ci.org/cloudify-cosmo/wagon.svg?branch=master
   :target: https://travis-ci.org/cloudify-cosmo/wagon
.. |PyPI| image:: http://img.shields.io/pypi/dm/wagon.svg
   :target: http://img.shields.io/pypi/dm/wagon.svg
.. |PypI| image:: http://img.shields.io/pypi/v/wagon.svg
   :target: http://img.shields.io/pypi/v/wagon.svg
