# Wagon

[![Build Status](https://travis-ci.org/cloudify-cosmo/wagon.svg?branch=master)](https://travis-ci.org/cloudify-cosmo/wagon)
[![Build status](https://ci.appveyor.com/api/projects/status/xf1hp1bekf3qhtr8/branch/master?svg=true)](https://ci.appveyor.com/project/Cloudify/wagon/branch/master)
[![PyPI version](http://img.shields.io/pypi/v/wagon.svg)](https://pypi.python.org/pypi/wagon)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/wagon.svg)](https://img.shields.io/pypi/pyversions/wagon.svg)
[![Requirements Status](https://requires.io/github/cloudify-cosmo/wagon/requirements.svg?branch=master)](https://requires.io/github/cloudify-cosmo/wagon/requirements/?branch=master)
[![Code Coverage](https://codecov.io/github/cloudify-cosmo/wagon/coverage.svg?branch=master)](https://codecov.io/github/cloudify-cosmo/wagon?branch=master)
[![Code Quality](https://landscape.io/github/cloudify-cosmo/wagon/master/landscape.svg?style=flat)](https://landscape.io/github/cloudify-cosmo/wagon)
[![Is Wheel](https://img.shields.io/pypi/wheel/wagon.svg?style=flat)](https://pypi.python.org/pypi/wagon)


A wagon (also spelt waggon in British and Commonwealth English) is a heavy four-wheeled vehicle pulled by draught animals, used for transporting goods, commodities, agricultural materials, supplies, and sometimes people. Wagons are distinguished from carts, which have two wheels, and from lighter four-wheeled vehicles primarily for carrying people, such as carriages.

or.. it is just a set of (Python) Wheels.

NOTE: To accommodate for the inconsistencies between wagon and pip, and to allow for additional required functionality, we will have to perform breaking changes until we can release v1.0.0. Please make sure you hardcode your wagon versions up until then.

## Incentive

Cloudify Plugins are packaged as sets of Python [Wheels](https://packaging.python.org/en/latest/distributing.html#wheels) in tar.gz/zip archives and so we needed a tool to create such entities; hence, Wagon.


## Requirements

* Wagon requires pip 1.4+ to work as this is the first version of pip to support Wheels.
* Wagon supports Linux, Windows and OSX on Python 2.7 and 3.4+. Python 2.5 will not be supported as it is not supported by pip. Python 2.6.x is not longer supported as wheel itself doesn't support it.
* Wagon is currently tested on both Linux and Windows (via Travis and AppVeyor).
* To be able to create Wagons of Wheels which include C extensions on Windows, you must have the [C++ Compiler for Python](http://www.microsoft.com/en-us/download/details.aspx?id=44266) installed.
* To be able to create Wagons of Wheels which include C extensions on Linux or OSX, you must have the required compiler installed depending on your base distro. Usually:
    * RHEL based required `gcc` and `python-devel`.
    * Debian based require `gcc` and `python-dev`.
    * Other linux distributions will usually require `gcc` but might require additional packages.
    * OSX requires `gcc`.


## Installation

```shell
pip install wagon

# latest development version
pip install http://github.com/cloudify-cosmo/wagon/archive/master.tar.gz
```

### Backward Compatilibity

NOTE: pip 10.x breaks wagon<=0.7.0 due to the removal of the `--use-wheel`. If you're using pip>=10.x, please make sure you use wagon>=0.8.0. Also, if you're using pip<=7.x, use wagon<=0.7.0.

NOTE: wagon>=0.7.0 drops support for Python 2.6, 3.2 and 3.3 since Wheel itself no longer supports these versions. Please use wagon<=0.6.1 if you still need to support those versions.


## Usage

NOTE: Currently, Wagon allows to pass arbitrary args to `pip wheel` and `pip install`. The way in which this is implemented is inconsistent with pip's implementation (wagon just allows passing a `-a` flag for all args.) This will be changed in the future to correspond to pip's implementation. See https://github.com/cloudify-cosmo/wagon/issues/70 for more information.

```bash
$ wagon
usage: wagon [-h] [-v] {create,install,validate,show,repair} ...

Create and install wheel based packages with their dependencies

positional arguments:
  {create,install,validate,show,repair}
    create              Create a Wagon archive
    install             Install a Wagon archive
    validate            Validate a wagon archive
    show                Print out the metadata of a wagon
    repair              Repair a Wagon archive

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Set verbose logging level (default: False)

...
```


### Create Packages

```bash
$ wagon create flask
...

Creating archive for flask...
Retrieving source...
Source is: Flask
Downloading Wheels for Flask...
Collecting Flask
Using cached Flask-0.12-py2.py3-none-any.whl
Saved /tmp/tmpcYHwh0/Flask/wheels/Flask-0.12-py2.py3-none-any.whl
Collecting itsdangerous>=0.21 (from Flask)
Saved /tmp/tmpcYHwh0/Flask/wheels/itsdangerous-0.24-cp27-none-any.whl
Collecting click>=2.0 (from Flask)
Using cached click-6.7-py2.py3-none-any.whl
Saved /tmp/tmpcYHwh0/Flask/wheels/click-6.7-py2.py3-none-any.whl
...
Skipping MarkupSafe, due to already being wheel.
Platform is: linux_x86_64
Generating Metadata...
Writing metadata to file: /tmp/tmpcYHwh0/Flask/package.json
Creating tgz archive: ./Flask-0.12-py27-none-linux_x86_64.wgn...
Removing work directory...
Wagon created successfully at: ./Flask-0.12-py27-none-linux_x86_64.wgn

...
```

#### Requirement Files

NOTE: Beginning with `Wagon 0.5.0`, Wagon no longer looks up requirement files within archives or in the local directory when creating wagons. You must expclitly specify requirement files.

You can provide multiple requirement files to be resolved by using the `-r` flag (multiple times).

#### Editable Mode

Wagon doesn't currently provide a way for packaging packages that are in editable mode.
So, for instance, providing a `dev-requirements` file which contains a `-e DEPENDENCY` requirement will not be taken into consideration. This is not related to wagon but rather to the default `pip wheel` implementation stating that it will be "Skipping bdist_wheel for #PACKAGE#, due to being editable".


### Install Packages

```bash
$ wagon install Flask-0.12-py27-none-linux_x86_64.wgn
...

Installing Flask-0.12-py27-none-linux_x86_64.wgn
Retrieving source...
Extracting tgz Flask-0.12-py27-none-linux_x86_64.wgn to /tmp/tmplXv6Fi...
Source is: /tmp/tmplXv6Fi/Flask
Validating Platform linux_x86_64 is supported...
Installing Flask...
Installing within current virtualenv
Collecting Flask
Collecting itsdangerous>=0.21 (from Flask)
...
Installing collected packages: itsdangerous, Werkzeug, Flask
Successfully installed Flask-0.12 Werkzeug-0.11.15 itsdangerous-0.24

...
```

NOTE: `--pre` is appended to the installation command to enable installation of prerelease versions.

#### Installing Manually

While wagon provides a generic way of installing wagon created archives, you might not want to use the installer as you might not wish to install wagon on your application servers. Installing the package manually via pip is as easy as running (for example):

```bash
# For Linux (Windows wagon archives are zip files)
tar -xzvf ./Flask-0.12-py27-none-linux_x86_64.wgn
pip install --no-index --find-links Flask/wheels flask
```


### Validate Packages

The `validate` function provides shallow validation of a Wagon archive. Basically, that all required wheels for a package are present and that the package is installable.

This shallow validation should, at the very least, verify that a Wagon archive is not corrupted. Note that the `--validate` flag provided with the `create` function uses this same validation method. Also note that validation must take place only on an OS distribution which supports the wagon archive if it contains C extensions. For instance, a win32 specific wagon archive will fail to validate on a Linux machine.

`venv` Python's stdlib module must be installed for Wagon to be able to validate an archive to not pollute the current environment.

```bash
$ wagon validate Flask-0.12-py27-none-linux_x86_64.wgn
...

Validating Flask-0.12-py27-none-linux_x86_64.wgn
Retrieving source...
Extracting tgz Flask-0.12-py27-none-linux_x86_64.wgn to /tmp/tmp2gqpy1...
Source is: /tmp/tmp2gqpy1/Flask
Verifying that all required files exist...
Testing package installation...
Creating Virtualenv /tmp/tmpdPNDIi...
Using real prefix '/usr'
New python executable in /tmp/tmpdPNDIi/bin/python2
Also creating executable in /tmp/tmpdPNDIi/bin/python
Installing setuptools, pip, wheel...done.
Installing /tmp/tmp2gqpy1/Flask
Retrieving source...
Source is: /tmp/tmp2gqpy1/Flask
Validating Platform linux_x86_64 is supported...
Installing Flask...
Collecting Flask
...
Installing collected packages: itsdangerous, click, MarkupSafe, Jinja2, Werkzeug, Flask
Successfully installed Flask-0.12 Jinja2-2.9.2 MarkupSafe-0.23 Werkzeug-0.11.15 click-6.7 itsdangerous-0.24
Package Flask is installed in /tmp/tmpdPNDIi
Validation Passed!

...
```


### Show Metadata

Given a Wagon archive, this will print its metadata.

```bash
$ wagon show Flask-0.12-py27-none-linux_x86_64.wgn
...

{
    "archive_name": "Flask-0.12-py27-none-linux_x86_64.wgn",
    "build_server_os_properties": {
        "distribution": "antergos",
        "distribution_release": "archcode",
        "distribution_version": ""
    },
    "created_by_wagon_version": "0.6.0",
    "package_name": "Flask",
    "package_source": "flask",
    "package_version": "0.12",
    "supported_platform": "linux_x86_64",
    "supported_python_versions": [
        "py27"
    ],
    "wheels": [
        "MarkupSafe-0.23-cp27-cp27mu-linux_x86_64.whl",
        "Werkzeug-0.11.15-py2.py3-none-any.whl",
        "Jinja2-2.9.2-py2.py3-none-any.whl",
        "click-6.7-py2.py3-none-any.whl",
        "itsdangerous-0.24-cp27-none-any.whl",
        "Flask-0.12-py2.py3-none-any.whl"
    ]
}

...
```

### Repair Wagon

`auditwheel` is a tool (currently under development) provided by pypa to "repair" wheels to support multiple linux distributions. Information on auditwheel is provided [here](https://github.com/pypa/auditwheel).

Wagon provides a way to repair a wagon by iterating over its wheels and fixing all of them.

NOTE! The repair command is EXPERIMENTAL in Wagon. It isn't fully tested and relies on `auditwheel`, which is, in itself, somewhat experimental. Read [https://www.python.org/dev/peps/pep-0513/](https://www.python.org/dev/peps/pep-0513/) for more info.

For more information, see [Linux Support for compiled wheels](#linux-support-for-compiled-wheels) below.

The following example was executed on a container provided for wheel-auditing purposes which you can be run like so:

```bash
$ docker run -it -v `pwd`:/io quay.io/pypa/manylinux1_x86_64 /bin/bash
```

```bash
$ /opt/python/cp27-cp27m/bin/pip install wagon
...

$ /opt/python/cp27-cp27m/bin/wagon repair cloudify-4.0a10-py27-none-linux_x86_64.wgn -v
...

Repairing: cloudify-4.0a10-py27-none-linux_x86_64.wgn
Retrieving source...
Extracting tgz cloudify-4.0a10-py27-none-linux_x86_64.wgn to /tmp/tmpDZ4kNC...
Source is: /tmp/tmpDZ4kNC/cloudify
Repairing PyYAML-3.10-cp27-cp27m-linux_x86_64.whl
Previous filename tags: linux_x86_64
New filename tags: manylinux1_x86_64
Previous WHEEL info tags: cp27-cp27m-linux_x86_64
New WHEEL info tags: cp27-cp27m-manylinux1_x86_64
...
Generating Metadata...
Writing metadata to file: /tmp/tmpDZ4kNC/cloudify/package.json
Creating tgz archive: /cloudify-4.0a10-py27-none-manylinux1_x86_64.wgn...
Wagon created successfully at: /cloudify-4.0a10-py27-none-manylinux1_x86_64.wgn

...
```

## Naming and Versioning

### Source: PyPI

When providing a PyPI source, it can either be supplied as `PACKAGE_NAME==PACKAGE_VERSION` after which wagon then applies the correct name and version to the archive according to the two parameters; or `PACKAGE_NAME`, after which the `PACKAGE_VERSION` will be extracted from the downloaded wheel.

### Source: Else

For local path and URL sources, the name and version are automatically extracted from the setup.py file.

NOTE: This means that when supplying a local path, you must supply a path to the root of where your setup.py file resides.

NOTE: If using a URL, it must be a URL to a tar.gz/zip file structured like a GitHub tar.gz/zip archive (e.g. https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/master.tar.gz)


## Metadata File and Wheels

A Metadata file is generated for the archive and looks somewhat like this:

```
{
    "archive_name": "cloudify_script_plugin-1.2-py27-none-linux_x86_64.wgn",
    "build_server_os_properties": {
        "distribution": "ubuntu",
        "distribution_release": "trusty",
        "distribution_version": "14.04"
    },
    "package_name": "cloudify-script-plugin",
    "package_source": "cloudify-script-plugin==1.2",
    "package_version": "1.2",
    "supported_platform": "any",
    "supported_python_versions": [
        "py26",
        "py27"
    ],
    "wheels": [
        "proxy_tools-0.1.0-py2-none-any.whl",
        "pyzmq-14.7.0-cp27-none-linux_x86_64.whl",
        "bottle-0.12.7-py2-none-any.whl",
        "networkx-1.8.1-py2-none-any.whl",
        "requests-2.5.1-py2.py3-none-any.whl",
        "PyYAML-3.10-cp27-none-linux_x86_64.whl",
        "pika-0.9.13-py2-none-any.whl",
        "jsonschema-2.3.0-py2.py3-none-any.whl",
        "cloudify_dsl_parser-3.2-py2-none-any.whl",
        "cloudify_rest_client-3.2-py2-none-any.whl",
        "cloudify_script_plugin-1.2-py2-none-any.whl"
    ]
}
```

* The wheels to be installed reside in the zip file under 'wheels/*.whl'.
* The Metadata file resides in the archive file under 'package.json'.
* The installer uses the metadata file to check that the platform fits the machine the package is being installed on.
* OS Properties only appear when creating compiled Linux packages (see Linux Distributions section). In case of a non-linux platform (e.g. win32, any), null values will be supplied for OS properties.
* The distribution identification is done using `platform.linux_distribution`, which is deprecated and will be removed in Python 3.7. `https://github.com/nir0s/distro` is a successor of that functionality and can be installed by running `pip install wagon[dist]`. We currently use distro only if it is instsalled. In later versions of wagon, we will stop using `platform.linux_distribution` altogether.


## Archive naming convention and Platform

The archive is named according to the Wheel naming convention described in [PEP0491](https://www.python.org/dev/peps/pep-0491/#file-name-convention).

Example Output Archive: `cloudify_aws_plugin-1.4.3-py27-none-any.wgn`


* `{python tag}`: The Python version is set by the Python running the packaging process. That means that while a package might run on both py27 and py33 (for example), since the packaging process took place using Python 2.7, only py27 will be appended to the name. A user can also explicitly provide the supported Python versions for the package via the `pyver` flag.
* `{platform tag}`: Normally, the platform (e.g. `linux_x86_64`, `win32`) is set for each specific wheel. To know which platform the package with its dependencies can be installed on, all wheels are checked. If a specific wheel has a platform property other than `any`, that platform will be used as the platform of the package. Of course, we assume that there can't be wheels downloaded or created on a specific machine platform that belongs to two different platforms.
* `{abi tag}`: Note that the ABI tag is currently ignored and will always be `none`. This might be changed in the future to support providing an ABI tag.


## Linux Support for compiled wheels

Example Output Archive: `cloudify_fabric_plugin-1.2.1-py27-none-linux_x86_64.wgn`

Wheels which require compilation of C-extensions and are compiled on Linux are not uploaded to PyPI due to variations between compilation environments on different distributions and links to varying system libraries.

To overcome that (partially), when running Wagon on Linux and the package requires compilation, the metadata provides the distribution, version and release name of the OS that the archive was created on (via `platform.linux_distribution()` and `https://github.com/nir0s/distro`). Statistically speaking, this should provide the user with the information they need to know which OS the package can be installed on. Obviously, this is not true for cases where non-generic compilation methods are used on the creating OS but otherwise should work, and should specifically always work when both compilation environment and Python version are similar on the creating and installing OS - which, we generally recommend.

What this practically means, is that in most cases using the metadata to compare the distro, distro version, and the Python version under which the package is installed would allow a user to use Wagon rather safely. Of course, Wagon provides no guarantee whatsoever as to whether this will actually work or not and users must test their archives.

That being said, Wagon is completely safe for creating and installing Pure-Python package archives for any platform, and, due to the nature of Wheels, packages compiled for OS X or Windows on corresponding architectures.


## Python API

Wagon provides an easy to use API.
You can pass a `verbose` True/False flag to each of these functions.

### Create

```python

import wagon

source = 'flask==0.10.1'

wagon.set_verbose(True)

archive_path = wagon.create(
    source,
    requirement_files=None,
    force=False,
    keep_wheels=False,
    archive_destination_dir='.',
    python_versions=None,
    validate_archive=False,
    wheel_args='',
    archive_format='tar.gz')
```

### Install

```python

import wagon

source = 'http://my-wagons.com/Flask-0.10.1-py27-none-linux_x86_64.wgn'

wagon.install(
    source,
    venv=None,
    requirement_files=None,
    upgrade=False,
    ignore_platform=False,
    install_args='')
```

### Validate

```python

import wagon

source = 'http://my-wagons.com/Flask-0.10.1-py27-none-linux_x86_64.wgn'

result = wagon.validate(source=source)  # True if validation successful, else False
```

### Showmeta

```python

import wagon

source = 'http://my-wagons.com/Flask-0.10.1-py27-none-linux_x86_64.wgn'

metadata = wagon.show(source=source)
print(metadata)
```


### Repair

```python

import wagon

source = 'http://my-wagons.com/Flask-0.10.1-py27-none-linux_x86_64.wgn'
repaired_archive_path = wagon.repair(source=source, validate=True)
```


## Testing

NOTE: Running the tests require an internet connection
NOTE: Some tests check if the `CI` env var is set. If not, they will not run.

```shell
git clone git@github.com:cloudify-cosmo/wagon.git
cd wagon
pip install tox
tox
```

## Contributions..

..are always welcome. We're looking to:

* Provide the most statistically robust way of identification and installation of Linux compiled Wheels.

