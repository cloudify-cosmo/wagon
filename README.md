# Cloudify Plugin Packager

This tool creates Cloudify plugin packages (Currently, only tested on Linux).

Cloudify Plugins are packaged as sets of Python [Wheels](https://packaging.python.org/en/latest/distributing.html#wheels) in tar.gz files.

## Usage

```shell
cfy-pp create --help

Usage: cfy-pp create [OPTIONS]

  Creates a plugin package (tar.gz)

  Example sources:
  - http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/master.tar.gz
  - ~/repos/cloudify-script-plugin
  - cloudify-script-plugin==1.2.1

  - If source is URL, download and extract it and get module name and version
  from setup.py.
  - If source is a local path, get module name and version from
  setup.py.
  - If source is module_name==module_version, use them as name and
  version.

Options:
  -s, --source TEXT             Source URL, Path or Module name.  [required]
  --pre                         Whether to pack a prerelease of the plugin.
  -r, --requirements-file TEXT  Whether to also pack wheels from a
                                requirements file.
  -f, --force                   Force overwriting existing output file.
  --keep-wheels                 Force overwriting existing output file.
  -o, --output-directory TEXT   Output directory for the tar file.
  -v, --verbose
  --help                        Show this message and exit.
```

## Examples
```shell
# create a plugin package by retrieving the source from PyPI and keep the downloaded wheels (kept under <cwd>/plugin)
cfy-pp create -s cloudify-script-plugin==1.2 --keep-wheels
# create a plugin package by retrieving the source from a URL.
cfy-pp create -s http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.tar.gz
# create a plugin package by retrieving the source from a local path and output the tar.gz file to /tmp/<PLUGIN>.tar.gz (defaults to <cwd>/<PLUGIN>.tar.gz)
cfy-pp create -s ~/repos/cloudify-script-plugin/ -o /tmp/
```

The output package of all three commands should be `cloudify_script_plugin-1.2-py27-none-any.tar.gz` if running under Python 2.7.x.

## Naming and Versioning

### Source: PyPI
When providing a PyPI source, it must be supplied as PLUGIN_NAME==PLUGIN_VERSION. The packager then applies the correct name and version to the package according to the two parameters.

### Source: Else
For local path and URL sources, the name and version are automatically extracted from the setup.py file.

NOTE: This means that when supplying a local path, you must supply a path to the root of where your setup.py file resides.

## Metadata File and Wheels
A Metadata file is generated for the plugin and looks somewhat like this:

```
{
    "archive_name": "cloudify_script_plugin-1.2-py27-none-any.tar.gz",
    "platform": "any",
    "plugin_name": "cloudify-script-plugin",
    "plugin_source": "cloudify-script-plugin==1.2",
    "plugin_version": "1.2",
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

The metadata file is used by our plugin installer to identify which plugin to install under certain conditions.
PROVIDE MORE INFORMATION HERE ABOUT THE PLUGIN INSTALLER (AS A LINK, PROBABLY!)

* The wheels to be installed as a part of the plugin reside in the tar.gz file under 'wheels/*.whl'.
* The Metadata file resides in the tar.gz file under 'plugin.json'

## Package naming convention and Platform
The tar.gz archive is named according to the Wheel naming convention described in [PEP0427](https://www.python.org/dev/peps/pep-0427/#file-name-convention) aside from two fields:

Example: `cloudify_fabric_plugin-1.2.1-py27-none-linux_x86_64.tar.gz`

* `{python tag}`: The Python version is set by the Python running the packaging process. That means that while a plugin can run on both py27 and py33 (for example), since the packaging process took place using Python 2.7, only py27 will be appended to the name. Note that we will be providing a way for the user to provide the supported Python versions explicitly.
* `{platform tag}`: The platform (e.g. `linux_x86_64`, `win32`) is set for a specific wheel. To know which platform the plugin can be installed on, all wheels are checked. If a specific wheel has a platform property other than `any`, that platform will be used as the platform of the package. Of course, we assume that there can't be wheels downloaded or created on a specific machine platform that belongs to two different platforms.