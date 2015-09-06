# get module path (pypi, github, local) from cli
# wheel it to the destination directory
# tar the wheel with the following name format: cloudify_#module_name#_#module_version#.tar.gz  # NOQA

import logger
import logging
import os
import sys
import shutil
import click
import uuid
import tempfile
import json

import utils
import codes


DEFAULT_PLUGIN_PATH = 'plugin'
DEFAULT_WHEELS_PATH = '{0}/wheels'.format(DEFAULT_PLUGIN_PATH)
TAR_NAME_FORMAT = '{0}-{1}-{2}-none-{3}.tar.gz'

lgr = logger.init()


class PluginPackager():
    def __init__(self, source, verbose=False):
        if verbose:
            lgr.setLevel(logging.DEBUG)
        else:
            lgr.setLevel(logging.INFO)
        self.source = source

    def create(self, pre=False, requirements_file=None, force=False,
               keep_wheels=False, tar_destination_directory='.'):
        lgr.info('Creating plugin package for {0}...'.format(self.source))
        source = self.get_source(self.source)
        module_name, module_version = \
            self.get_source_name_and_version(source)

        self.handle_output_directory(DEFAULT_PLUGIN_PATH, force)

        utils.wheel(source, pre, requirements_file, DEFAULT_WHEELS_PATH)
        wheels = utils.get_downloaded_wheels(DEFAULT_WHEELS_PATH)
        platform = utils.get_platform_for_set_of_wheels(
            DEFAULT_WHEELS_PATH)

        tar_file = self.set_tar_name(module_name, module_version, platform)
        tar_path = os.path.join(tar_destination_directory, tar_file)

        self.handle_output_file(tar_path, force)

        lgr.info('The following wheels were downloaded '
                 'or created:\n{0}'.format(json.dumps(
                     wheels, indent=4, sort_keys=True)))
        self.generate_metadata_file(wheels, platform)

        utils.tar(DEFAULT_PLUGIN_PATH, tar_path)

        if not keep_wheels:
            lgr.debug('Cleaning up...')
            shutil.rmtree(DEFAULT_PLUGIN_PATH)
        lgr.info('Process complete!')

    def generate_metadata_file(self, wheels, platform):
        """This generates a metadata file for the plugin.

        The metadata will be used by Cloudify's plugin installer
        to identify the plugin to install by its properties.
        """
        lgr.debug('Generating Metadata...')
        metadata = {
            'archive_name': self.tar,
            'platform': platform,
            'plugin_name': self.name,
            'plugin_source': self.source,
            'plugin_version': self.version,
            'wheels': wheels
        }
        formatted_metadata = json.dumps(metadata, indent=4, sort_keys=True)
        lgr.debug('Metadata is: {0}'.format(formatted_metadata))
        output_path = os.path.join(DEFAULT_PLUGIN_PATH, 'plugin.json')
        with open(output_path, 'w') as f:
            lgr.info('Writing metadata to file: {0}'.format(output_path))
            f.write(formatted_metadata)

    def set_tar_name(self, module_name, module_version, platform):
        """Sets the format of the output tar file.

        We should aspire for the name of the tar to be
        as compatible as possible with the wheel naming convention
        described here:
        https://www.python.org/dev/peps/pep-0427/#file-name-convention,
        as we've basically providing a "wheel" of our plugin.
        """
        self.python = utils.get_python_version()
        self.tar = TAR_NAME_FORMAT.format(
            module_name.replace('-', '_'), module_version,
            self.python, platform)
        return self.tar

    def get_source(self, source):
        """If necessary, downloads and extracts the source.

        If the source is a url to a module's tar file,
        this will download the source and extract it to a temporary directory.
        """
        split = source.split('://')
        schema = split[0]
        lgr.debug('Retrieving source...')
        if schema in ['http', 'https']:
            tmpdir = tempfile.mkdtemp()
            tmpfile = os.path.join(tmpdir, str(uuid.uuid4()))
            utils.download_file(source, tmpfile)
            utils.untar(tmpfile)
            source = os.path.join(
                tmpdir, [d for d in os.walk(tmpdir).next()[1]][0])
        elif os.path.isdir(source):
            source = os.path.expanduser(source)
        lgr.debug('Source is: {0}'.format(source))
        return source

    def get_source_name_and_version(self, source):
        """Retrieves the source plugin's name and version.

        If the source is a path, the name and version will be retrieved
        by querying the setup.py file in the path.

        If the source is of format MODULE==VERSION, they will be used as
        the name and version.
        """
        if os.path.isfile(os.path.join(source, 'setup.py')):
            lgr.debug('setup.py file found. Retrieving name and version...')
            stppy = os.path.join(source, 'setup.py')
            self.name = utils.run('{0} --name'.format(
                stppy)).aggr_stdout.strip('\n')
            self.version = utils.run('{0} --version'.format(
                stppy)).aggr_stdout.strip('\n')
        elif '==' in source:
            lgr.debug('Retrieving name and version...')
            self.name, self.version = source.split('==')
        else:
            lgr.error('Source must either be a folder containing a setup.py '
                      'file or of format MODULE_NAME==MODULE_VERSION.')
            sys.exit(1)
        lgr.info('Module name: {0}'.format(self.name))
        lgr.info('Module version: {0}'.format(self.version))
        return self.name, self.version

    def handle_output_file(self, destination_tar, force):
        """Handles the output tar.

        removes the output file if required, else, notifies
        that it already exists.

        :param string destination_tar: destination tar path
        :param bool force: whether to force creation or not if
         it already exists.
        """
        if os.path.isfile(destination_tar) and force:
            lgr.info('Removing previous agent package...')
            os.remove(destination_tar)
        if os.path.exists(destination_tar):
                lgr.error('Destination tar already exists: {0}. You can use '
                          'the -f flag to overwrite.'.format(destination_tar))
                sys.exit(codes.errors['tar_already_exists'])

    def handle_output_directory(self, wheels_path, force):
        if os.path.isdir(wheels_path):
            if force:
                shutil.rmtree(wheels_path)
            else:
                lgr.error('Directory {0} already exists. Please remove it and '
                          'run this again.'.format(DEFAULT_WHEELS_PATH))
                sys.exit(1)


@click.group()
def main():
    pass


@click.command()
@click.option('-s', '--source', required=True,
              help='Source URL, Path or Module name.',
              envvar='CLOUDIFY_PLUGIN_SOURCE')
@click.option('--pre', default=False, is_flag=True,
              help='Whether to pack a prerelease of the plugin.',
              envvar='CLOUDIFY_PLUGIN_PACK_PRE')
@click.option('-r', '--requirements-file',
              help='Whether to also pack wheels from a requirements file.',
              envvar='CLOUDIFY_PLUGIN_REQUIREMENTS_FILE')
@click.option('-f', '--force', default=False, is_flag=True,
              help='Force overwriting existing output file.',
              envvar='CLOUDIFY_PLUGIN_PACK_FORCE')
@click.option('--keep-wheels', default=False, is_flag=True,
              help='Force overwriting existing output file.',
              envvar='CLOUDIFY_PLUGIN_KEEP_WHEELS')
@click.option('-o', '--output-directory', default='.',
              help='Output directory for the tar file.',
              envvar='CLOUDIFY_PLUGIN_TAR_OUTPUT_DIR')
@click.option('-v', '--verbose', default=False, is_flag=True)
def create(source, pre, requirements_file, force, keep_wheels,
           output_directory, verbose):
    """Creates a plugin package (tar.gz)

    \b
    Example sources:
    - http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/master.tar.gz
    - ~/repos/cloudify-script-plugin
    - cloudify-script-plugin==1.2.1

    \b
    Note:
    - If source is URL, download and extract it and get module name and version
     from setup.py.
    - If source is a local path, get module name and version from setup.py.
    - If source is module_name==module_version, use them as name and version.
    """
    # TODO: Let the user provide supported Python versions.
    # TODO: Let the user provide supported Architectures.
    packager = PluginPackager(source, verbose)
    packager.create(pre, requirements_file, force, keep_wheels,
                    output_directory)


main.add_command(create)
