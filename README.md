# Wagon

A wagon (also spelt waggon in British and Commonwealth English) is a heavy four-wheeled vehicle pulled by draught animals, used for transporting goods, commodities, agricultural materials, supplies, and sometimes people. Wagons are distinguished from carts, which have two wheels, and from lighter four-wheeled vehicles primarily for carrying people, such as carriages.

* Master Branch [![Build Status](https://travis-ci.org/cloudify-cosmo/wagon.svg?branch=master)](https://travis-ci.org/cloudify-cosmo/wagon)
* PyPI [![PyPI](http://img.shields.io/pypi/dm/wagon.svg)](http://img.shields.io/pypi/dm/wagon.svg)
* Version [![PypI](http://img.shields.io/pypi/v/wagon.svg)](http://img.shields.io/pypi/v/wagon.svg)


Cloudify Plugins are packaged as sets of Python [Wheels](https://packaging.python.org/en/latest/distributing.html#wheels) in tar.gz archives and so we needed a tool to create such entities; hence, Wagon.

* Wagon currently supports Python 2.6.x and Python 2.7.x.
* Wagon is currently only tested on Linux but might work on other platforms.


## Installation

```shell
pip install wagon
```


## Usage

### Create Packages

```shell
wagon create --help
```

#### Examples

```shell
# create an archive by retrieving the source from PyPI and keep the downloaded wheels (kept under <cwd>/plugin)
wagon create -s cloudify-script-plugin==1.2 --keep-wheels -v
# create an archive by retrieving the source from a URL and creating wheels from requirement files found within the archive. Then, validation of the archive takes place.
wagon create -s http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.tar.gz -r . --validate
# create an archive by retrieving the source from a local path and output the tar.gz file to /tmp/<MODULE>.tar.gz (defaults to <cwd>/<MODULE>.tar.gz) and provides explicit Python versions supported by the module (which usually defaults to the first two digits of the Python version used to create the archive.)
wagon create -s ~/modules/cloudify-script-plugin/ -o /tmp/ --pyver 33 --pyver 26 --pyver 27
```

### Install Packages

```shell
wagon install --help
```

#### Examples

```shell
# install a module from a local archive tar file and upgrade if already installed. Also, ignore the platform check which would force a module (whether it is or isn't compiled for a specific platform) to be installed.
wagon install -s ~/tars/cloudify_script_plugin-1.2-py27-none-any.tar.gz --upgrade --ignore-platform
# install a module from a url into an existing virtualenv.
wagon install -s http://me.com/cloudify_script_plugin-1.2-py27-none-any.tar.gz --virtualenv my_venv -v
```

#### Installing Manually

While wagon provides a generic way of installing wagon created archives, you might not want to use the installer as you might not wish to install wagon on your application servers. Installing the module manually via pip is as easy as running (for example):

```shell
tar -xzvf http://me.com/cloudify_script_plugin-1.2-py27-none-any.tar.gz
pip install --no-index --find-links cloudify-script-plugin/wheels cloudify-script-plugin
```


### Validate Packages

```sheel
wagon validate --help
```

The `validate` function provides shallow validation of a Wagon archive. Basically, it checks that some keys in the metadata are found, that all required wheels for a module are present and that the module is installable. It obviously does not check for a module's functionality.

This shallow validation should, at the very least, allow a user to be sure that a Wagon archive is not corrupted.

Note that the `--validate` flag provided with the `create` function uses this same validation method.


#### Examples

```shell
# validate that an archive is a wagon compatible package
wagon validate -s ~/tars/cloudify_script_plugin-1.2-py27-none-any.tar.gz
# validate from a url
wagon validate -s http://me.com/cloudify_script_plugin-1.2-py27-none-any.tar.gz
```

## Naming and Versioning

### Source: PyPI
When providing a PyPI source, it must be supplied as MODULE_NAME==MODULE_VERSION. wagon then applies the correct name and version to the archive according to the two parameters.

### Source: Else
For local path and URL sources, the name and version are automatically extracted from the setup.py file.

NOTE: This means that when supplying a local path, you must supply a path to the root of where your setup.py file resides.

NOTE: If using a URL, it must be a URL to a tar.gz file structured like a GitHub tar.gz archive (e.g. https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/master.tar.gz)


## Metadata File and Wheels

A Metadata file is generated for the archive and looks somewhat like this:

```
{
    "archive_name": "cloudify_script_plugin-1.2-py27-none-any-ubuntu-trusty.tar.gz",
    "build_server_os_properties": {
        "distribution": "ubuntu",
        "distribution_release": "trusty",
        "distribution_version": "14.04"
    },
    "module_name": "cloudify-script-plugin",
    "module_source": "cloudify-script-plugin==1.2",
    "module_version": "1.2",
    "supported_platform": "any",
    "supported_python_versions": [
        "py26",
        "py27"
    ],
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
```

* The wheels to be installed reside in the tar.gz file under 'wheels/*.whl'.
* The Metadata file resides in the tar.gz file under 'module.json'.
* The installer uses the metadata file to check that the platform fits the machine the module is being installed on.
* OS Properties only appear when creating under Linux (see Linux Distributions section.)


## Archive naming convention and Platform

The archive is named according to the Wheel naming convention described in [PEP0491](https://www.python.org/dev/peps/pep-0491/#file-name-convention).

Example Output Archive: `cloudify_fabric_plugin-1.2.1-py27-none-any-none-none.tar.gz`

* `{python tag}`: The Python version is set by the Python running the packaging process. That means that while a module might run on both py27 and py33 (for example), since the packaging process took place using Python 2.7, only py27 will be appended to the name. A user can also explicitly provide the supported Python versions for the module via the `pyver` flag.
* `{platform tag}`: The platform (e.g. `linux_x86_64`, `win32`) is set each specific wheel. To know which platform the module with its dependencies can be installed on, all wheels are checked. If a specific wheel has a platform property other than `any`, that platform will be used as the platform of the package. Of course, we assume that there can't be wheels downloaded or created on a specific machine platform that belongs to two different platforms.
* For Linux (see below), two additional tags are added: `{distribution tag}` and `{release tag}`. Note that these tags are NOT a part of the PEP.


## Linux Support for compiled wheels

Example Output Archive: `cloudify_fabric_plugin-1.2.1-py27-none-linux_x86_64-ubuntu-trusty.tar.gz`

Wheels which require compilation of C extensions and are compiled on Linux are not uploaded to PyPI due to variations between compilation environments on different distributions and links to varying system libraries.

To overcome that (partially), if running Wagon on Linux and the module requires compilation, the metadata and archive name both provide the distribution and release of the OS that the archive was created on (via platform.linux_distribution()). Statistically speaking, this should provide the user with the information they need to know which OS the module can be installed on. Obviously, this is not true for cases where non-generic compilation methods are used on the creating OS but otherwise should work, and should specifically always work when both compilation environment and Python version are similar on the creating and installing OS - which, we generally recommend.

What this partically means, is that in most cases, using the metadata to compare the distro, release and the Python version under which the module is installed would allow a user to use Wagon rather safely. Of course, Wagon provides no guarantee whatsoever as to whether this will actually work or not and users must test their archives.

That being said, Wagon is completely safe for creating and installing Pure Python module archives or, due to the nature of Wheels, modules compiled for OS X or Windows.


## Testing

NOTE: Running the tests require an internet connection

```shell
git clone git@github.com:cloudify-cosmo/wagon.git
cd wagon
pip install tox
tox
```

## Contributions..

..are always welcome. We're looking to:

* Support Python 3.x
* Provide the most statistically robust way of identification and installation of Linux compiled Wheels.
* Test on Windows (AppVeyor to come...)