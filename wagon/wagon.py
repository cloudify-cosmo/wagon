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

REQUIREMENT_FILE_NAMES = ['dev-requirements.txt', 'requirements.txt']
METADATA_FILE_NAME = 'module.json'
DEFAULT_WHEELS_PATH = 'wheels'
TAR_NAME_FORMAT = '{0}-{1}-{2}-none-{3}.tar.gz'

lgr = logger.init()


class Wagon():
    def __init__(self, source, verbose=False):
        if verbose:
            lgr.setLevel(logging.DEBUG)
        else:
            lgr.setLevel(logging.INFO)
        self.source = source

    def create(self, with_requirements=None, force=False,
               keep_wheels=False, tar_destination_directory='.',
               validate=False):
        lgr.info('Creating module package for {0}...'.format(self.source))
        source = self.get_source(self.source)
        module_name, module_version = \
            self.get_source_name_and_version(source)

        wheels_path = os.path.join(module_name, DEFAULT_WHEELS_PATH)
        self.handle_output_directory(module_name, force)

        if with_requirements == '.':
            with_requirements = self._get_default_requirement_files(source)
        elif with_requirements:
            with_requirements = [with_requirements]

        utils.wheel(source, with_requirements, wheels_path)
        wheels = utils.get_downloaded_wheels(wheels_path)
        platform = utils.get_platform_for_set_of_wheels(wheels_path)

        tar_file = self.set_tar_name(module_name, module_version, platform)
        tar_path = os.path.join(tar_destination_directory, tar_file)

        self.handle_output_file(tar_path, force)

        lgr.info('The following wheels were downloaded '
                 'or created:\n{0}'.format(json.dumps(
                     wheels, indent=4, sort_keys=True)))
        self.generate_metadata_file(wheels, platform)

        utils.tar(module_name, tar_path)

        if not keep_wheels:
            lgr.debug('Cleaning up...')
            shutil.rmtree(module_name)

        if validate:
            self.source = tar_path
            self.validate()
        lgr.info('Process complete!')
        return tar_path

    def install(self, virtualenv=None, requirements_file=None, upgrade=False):
        lgr.info('Installing {0}'.format(self.source))
        source = self.get_source(self.source)
        with open(os.path.join(source, 'module.json'), 'r') as f:
            metadata = json.loads(f.read())
        if metadata['supported_platform'] != 'any':
            machine_platform = utils.get_machine_platform()
            if machine_platform != metadata['supported_platform']:
                lgr.error('Platform unsupported for module ({0}).'.format(
                    machine_platform))
                sys.exit(1)

        wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
        utils.install_module(metadata['module_name'], wheels_path, virtualenv,
                             requirements_file, upgrade)

    def validate(self):
        lgr.info('Validating {0}'.format(self.source))
        source = self.get_source(self.source)
        with open(os.path.join(source, 'module.json'), 'r') as f:
            metadata = json.loads(f.read())
        wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
        validation_errors = []

        lgr.debug('Verifying that `supported_platform` key is in metadata...')
        if not metadata.get('supported_platform'):
            validation_errors.append(
                '`supported_platform` key not found in metadata file '
                'and is required for installation.')

        lgr.debug('Verifying that `module_name` key is in metadata...')
        if not metadata.get('module_name'):
            validation_errors.append(
                '`module_name` key not found in metadata file '
                'and is required for installation.')

        lgr.debug('Verifying that `wheels` key is in metadata...')
        if not metadata.get('wheels') or not \
                isinstance(metadata['wheels'], list):
            validation_errors.append(
                '`wheels` key missing or is not a list of wheels '
                'in metadata file. Cannot continue validation.')
            sys.exit(1)

        lgr.debug('Verifying that all required files exist...')
        for wheel in metadata['wheels']:
            if not os.path.isfile(os.path.join(wheels_path, wheel)):
                validation_errors.append('Missing wheel: {0}'.format(wheel))

        lgr.debug('Testing module installation...')
        tmpenv = tempfile.mkdtemp()
        try:
            utils.make_virtualenv(tmpenv)
        except Exception as ex:
            validation_errors.append(
                'Installation Validation Error: {0}'.format(str(ex)))
        finally:
            shutil.rmtree(tmpenv)

        if validation_errors:
            lgr.info('Validation failed!')
            for error in validation_errors:
                lgr.info(error)
            lgr.info('Source can be found at: {0}'.format(source))
            return False
        else:
            lgr.info('Validation Passed! (Cleaning up temporary files).')
            shutil.rmtree(os.path.dirname(source))
            return True

    @staticmethod
    def _get_default_requirement_files(source):
        if os.path.isdir(source):
            return [os.path.join(source, f) for f in REQUIREMENT_FILE_NAMES
                    if os.path.isfile(os.path.join(source, f))]

    def generate_metadata_file(self, wheels, platform):
        """This generates a metadata file for the module.
        """
        lgr.debug('Generating Metadata...')
        distro, version, release = utils.get_os_properties()
        metadata = {
            'archive_name': self.tar,
            'supported_platform': platform,
            'module_name': self.name,
            'module_source': self.source,
            'module_version': self.version,
            'build_server_os_properties': {
                'distribution': distro.lower(),
                'distribution_version': version.lower(),
                'distribution_release': release.lower()
            },
            'wheels': wheels
        }
        formatted_metadata = json.dumps(metadata, indent=4, sort_keys=True)
        lgr.debug('Metadata is: {0}'.format(formatted_metadata))
        output_path = os.path.join(self.name, METADATA_FILE_NAME)
        with open(output_path, 'w') as f:
            lgr.info('Writing metadata to file: {0}'.format(output_path))
            f.write(formatted_metadata)

    def set_tar_name(self, module_name, module_version, platform):
        """Sets the format of the output tar file.

        We should aspire for the name of the tar to be
        as compatible as possible with the wheel naming convention
        described here:
        https://www.python.org/dev/peps/pep-0427/#file-name-convention,
        as we've basically providing a "wheel" of our module.
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
        def extract_source(source, destination):
            utils.untar(source, destination)
            return os.path.join(
                destination, [d for d in os.walk(destination).next()[1]][0])

        lgr.debug('Retrieving source...')
        if '://' in source:
            split = source.split('://')
            schema = split[0]
            if schema in ['http', 'https']:
                tmpdir = tempfile.mkdtemp()
                tmpfile = os.path.join(tmpdir, str(uuid.uuid4()))
                try:
                    utils.download_file(source, tmpfile)
                    source = extract_source(tmpfile, tmpdir)
                finally:
                    os.remove(tmpfile)
            else:
                lgr.error('Source URL type {0} is not supported'.format(
                    schema))
                sys.exit(1)
        elif os.path.isfile(source) and source.endswith('.tar.gz'):
            tmpdir = tempfile.mkdtemp()
            source = extract_source(source, tmpdir)
        elif os.path.isdir(source):
            source = os.path.expanduser(source)
        elif '==' in source:
            pass
        else:
            lgr.error('Path to source {0} does not exist.'.format(source))
            sys.exit(1)
        lgr.debug('Source is: {0}'.format(source))
        return source

    def get_source_name_and_version(self, source):
        """Retrieves the source module's name and version.

        If the source is a path, the name and version will be retrieved
        by querying the setup.py file in the path.

        If the source is of format MODULE==VERSION, they will be used as
        the name and version.
        """
        if os.path.isfile(os.path.join(source, 'setup.py')):
            lgr.debug('setup.py file found. Retrieving name and version...')
            setuppy_path = os.path.join(source, 'setup.py')
            self.name = utils.run('python {0} --name'.format(
                setuppy_path)).aggr_stdout.strip('\n')
            self.version = utils.run('python {0} --version'.format(
                setuppy_path)).aggr_stdout.strip('\n')
        # TODO: maybe we don't want to be that explicit and allow using >=
        # TODO: or just a module name...
        elif '==' in source:
            lgr.debug('Retrieving name and version...')
            self.name, self.version = source.split('==')
        lgr.info('Module name: {0}'.format(self.name))
        lgr.info('Module version: {0}'.format(self.version))
        return self.name, self.version

    def handle_output_file(self, destination_tar, force):
        """Handles the output tar.

        removes the output file if required, else, notifies
        that it already exists.
        """
        if os.path.isfile(destination_tar) and force:
            lgr.info('Removing previous archive...')
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
                          'run this again.'.format(wheels_path))
                sys.exit(1)


@click.group()
def main():
    pass


@click.command()
@click.option('-s', '--source', required=True,
              help='Source URL, Path or Module name.')
@click.option('-r', '--with-requirements', required=False,
              help='Whether to also pack wheels from a requirements file.')
@click.option('-f', '--force', default=False, is_flag=True,
              help='Force overwriting existing output file.')
@click.option('--keep-wheels', default=False, is_flag=True,
              help='Keep wheels path after creation.')
@click.option('-o', '--output-directory', default='.',
              help='Output directory for the tar file.')
@click.option('--validate', default=False, is_flag=True,
              help='Runs a postcreation validation on the archive.')
@click.option('-v', '--verbose', default=False, is_flag=True)
def create(source, with_requirements, force, keep_wheels,
           output_directory, validate, verbose):
    """Creates a Python module's wheel base archive (tar.gz)

    \b
    Example sources:
    - http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/
    master.tar.gz
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
    packager = Wagon(source, verbose)
    packager.create(with_requirements, force, keep_wheels,
                    output_directory, validate)


@click.command()
@click.option('-s', '--source', required=True,
              help='Path or URL to source Wagon archive.')
@click.option('--virtualenv', default=None,
              help='Virtualenv to install in.')
@click.option('-r', '--requirements-file', required=False,
              help='A requirements file to install.')
@click.option('-u', '--upgrade', required=False, is_flag=True,
              help='Upgrades the module if it is already installed.')
@click.option('-v', '--verbose', default=False, is_flag=True)
def install(source, virtualenv, requirements_file, upgrade, verbose):
    """Installs a Wagon archive.
    """
    installer = Wagon(source, verbose)
    installer.install(virtualenv, requirements_file, upgrade)


@click.command()
@click.option('-s', '--source', required=True,
              help='Path or URL to source Wagon archive.')
@click.option('-v', '--verbose', default=False, is_flag=True)
def validate(source, verbose):
    """Validates an archive.
    """
    validator = Wagon(source, verbose)
    if not validator.validate():
        sys.exit(1)


main.add_command(create)
main.add_command(install)
main.add_command(validate)
