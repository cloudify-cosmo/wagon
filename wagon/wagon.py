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
METADATA_FILE_NAME = 'package.json'
DEFAULT_WHEELS_PATH = 'wheels'

lgr = logger.init()


class Wagon():
    """Main handler class.

    Provides the main four Wagon functions:
    - create
    - install
    - validate
    - get_metadata_from_archive
    """
    def __init__(self, source, verbose=False):
        """Source depends on the context in which
        the class is instantiated.

        When using `create`, source can be a path to a local setup.py
        containing directory; a URL to a GitHub like package archive or a
        name of a PyPI package in the format: PACKAGE_NAME==PACKAGE_VERSION.

        When using `install` or `validate`, source can be either a path
        to a local or a URL based Wagon archived tar.gz file.
        """
        if verbose:
            lgr.setLevel(logging.DEBUG)
        else:
            lgr.setLevel(logging.INFO)
        self.source = source

    def create(self, with_requirements=None, force=False,
               keep_wheels=False, excluded_packages=None,
               archive_destination_dir='.', python_versions=None,
               validate=False, wheel_args=None):
        """Creates a Wagon archive and returns its path.

        This currently only creates tar.gz archives. The `install`
        method assumes tar.gz when installing on Windows as well.

        Package name and version are extracted from the setup.py file
        of the `source` or from the PACKAGE_NAME==PACKAGE_VERSION if the source
        is a PyPI package.

        Excluded packages will be removed from the archive even if they are
        required for installation and their wheel names will be appended
        to the metadata for later analysis/validation.

        Supported `python_versions` must be in the format e.g [33, 27, 2, 3]..

        `force` will remove any excess dirs or archives before creation.

        `with_requirements` can be either a link/local path to a
        requirements.txt file or just `.`, in which case requirement files
        will be automatically extracted from either the GitHub archive URL
        or the local path provided provided in `source`.
        """
        lgr.info('Creating archive for {0}...'.format(self.source))
        source = self.get_source(self.source)
        package_name, package_version = \
            self.get_source_name_and_version(source)

        excluded_packages = excluded_packages or []
        if excluded_packages:
            lgr.warn('Note that excluding packages may make the archive '
                     'non-installable.')
        if package_name in excluded_packages:
            lgr.error('You cannot exclude the package '
                      'you are trying to wheel.')
            sys.exit(codes.errors['cannot_exclude_main_package'])

        wheels_path = os.path.join(package_name, DEFAULT_WHEELS_PATH)
        self.handle_output_directory(package_name, force)

        if with_requirements == '.':
            with_requirements = self._get_default_requirement_files(source)
        elif with_requirements:
            with_requirements = [with_requirements]

        wheels, excluded_wheels = utils.wheel(
            source, with_requirements, wheels_path, excluded_packages,
            wheel_args)
        self.platform = utils.get_platform_for_set_of_wheels(wheels_path)
        if python_versions:
            self.python_versions = ['py{0}'.format(v) for v in python_versions]
        else:
            self.python_versions = [utils.get_python_version()]

        archive_file = self.set_archive_name(package_name, package_version)
        archive_path = os.path.join(archive_destination_dir, archive_file)

        self.handle_output_file(archive_path, force)
        self.generate_metadata_file(wheels, excluded_wheels)

        utils.tar(package_name, archive_path)

        if not keep_wheels:
            lgr.debug('Cleaning up...')
            shutil.rmtree(package_name)

        if validate:
            self.source = archive_path
            self.validate()
        lgr.info('Process complete!')
        return archive_path

    def install(self, virtualenv=None, requirements_file=None, upgrade=False,
                ignore_platform=False, install_args=None):
        """Installs a Wagon archive.

        This can install in a provided `virtualenv` or in the current
        virtualenv in case one is currently active.

        `upgrade` is merely pip's upgrade.

        `ignore_platform` will allow to ignore the platform check, meaning
        that if an archive was created for a specific platform (e.g. win32),
        and the current platform is different, it will still attempt to
        install it.
        """
        lgr.info('Installing {0}'.format(self.source))
        source = self.get_source(self.source)
        with open(os.path.join(source, 'package.json'), 'r') as f:
            metadata = json.loads(f.read())
        supported_platform = metadata['supported_platform']
        if not ignore_platform and supported_platform != 'any':
            lgr.debug('Validating Platform {0} is supported...'.format(
                supported_platform))
            machine_platform = utils.get_machine_platform()
            if machine_platform != supported_platform:
                lgr.error('Platform unsupported for package ({0}).'.format(
                    machine_platform))
                sys.exit(codes.errors['unsupported_platform_for_package'])

        wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
        utils.install_package(
            metadata['package_name'], wheels_path, virtualenv,
            requirements_file, upgrade, install_args)

    def validate(self):
        """Validates a Wagon archive. Return True if succeeds, False otherwise.
        It also prints a list of all validation errors.

        This will test that some of the metadata is solid, that
        the required wheels are present within the archives and that
        the package is installable.

        Note that if the metadata file is corrupted, validation
        of the required wheels will be corrupted as well, since validation
        checks that the required wheels exist vs. the list of wheels
        supplied in the `wheels` key.
        """
        lgr.info('Validating {0}'.format(self.source))
        source = self.get_source(self.source)
        with open(os.path.join(source, 'package.json'), 'r') as f:
            metadata = json.loads(f.read())
        wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
        validation_errors = []

        lgr.debug('Verifying that `supported_platform` key is in metadata...')
        if not metadata.get('supported_platform'):
            validation_errors.append(
                '`supported_platform` key not found in metadata file '
                'and is required for installation.')

        lgr.debug('Verifying that `package_name` key is in metadata...')
        if not metadata.get('package_name'):
            validation_errors.append(
                '`package_name` key not found in metadata file '
                'and is required for installation.')

        lgr.debug('Verifying that `wheels` key is in metadata...')
        if not metadata.get('wheels') or not \
                isinstance(metadata['wheels'], list):
            validation_errors.append(
                '`wheels` key missing or is not a list of wheels '
                'in metadata file. Cannot continue validation.')
            sys.exit(codes.errors['wheels_key_missing'])

        lgr.debug('Verifying that all required files exist...')
        for wheel in metadata['wheels']:
            if not os.path.isfile(os.path.join(wheels_path, wheel)):
                validation_errors.append('Missing wheel: {0}'.format(wheel))

        lgr.debug('Testing package installation...')
        excluded_wheels = metadata.get('excluded_wheels')
        if excluded_wheels:
            for wheel in excluded_wheels:
                lgr.warn('Wheel {0} is excluded from the archive and is '
                         'possibly required for installation.'.format(wheel))
        tmpenv = tempfile.mkdtemp()
        try:
            utils.make_virtualenv(tmpenv)
            self.install(tmpenv)
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

    def get_metadata_from_archive(self):
        """Merely returns the metadata from the provided archive.

        This is used by the `showmeta` cli command to output the metadata.
        """
        lgr.debug('Retrieving Metadata for: {0}'.format(self.source))
        source = self.get_source(self.source)
        with open(os.path.join(source, 'package.json'), 'r') as f:
            metadata = json.loads(f.read())
        shutil.rmtree(source)
        return metadata

    @staticmethod
    def _get_default_requirement_files(source):
        if os.path.isdir(source):
            return [os.path.join(source, f) for f in REQUIREMENT_FILE_NAMES
                    if os.path.isfile(os.path.join(source, f))]

    def generate_metadata_file(self, wheels, excluded_wheels):
        """This generates a metadata file for the package.
        """
        lgr.debug('Generating Metadata...')
        metadata = {
            'archive_name': self.archive,
            'supported_platform': self.platform,
            'supported_python_versions': self.python_versions,
            'build_server_os_properties': {
                'distribution:': None,
                'distribution_version': None,
                'distribution_release': None,
            },
            'package_name': self.name,
            'package_version': self.version,
            'package_source': self.source,
            'wheels': wheels,
            'excluded_wheels': excluded_wheels
        }
        if utils.IS_LINUX and self.platform != 'any':
            distro, version, release = utils.get_os_properties()
            metadata.update(
                {'build_server_os_properties': {
                    'distribution': distro.lower(),
                    'distribution_version': version.lower(),
                    'distribution_release': release.lower()
                }})

        formatted_metadata = json.dumps(metadata, indent=4, sort_keys=True)
        lgr.debug('Metadata is: {0}'.format(formatted_metadata))
        output_path = os.path.join(self.name, METADATA_FILE_NAME)
        with open(output_path, 'w') as f:
            lgr.debug('Writing metadata to file: {0}'.format(output_path))
            f.write(formatted_metadata)

    def set_archive_name(self, package_name, package_version):
        """Sets the format of the output archive file.

        We should aspire for the name of the archive to be
        as compatible as possible with the wheel naming convention
        described here:
        https://www.python.org/dev/peps/pep-0491/#file-name-convention,
        as we've basically providing a "wheel" of our package.
        """
        package_name = package_name.replace('-', '_')
        python_versions = '.'.join(self.python_versions)

        archive = [package_name, package_version, python_versions, 'none',
                   self.platform, 'none', 'none']

        if utils.IS_LINUX and self.platform != 'any':
            distro, _, release = utils.get_os_properties()
            if distro:
                archive[5] = distro
            if release:
                archive[6] = release

        self.archive = '{0}.tar.gz'.format('-'.join(archive))
        return self.archive

    def get_source(self, source):
        """If necessary, downloads and extracts the source.

        If the source is a url to a package's tar file,
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
                sys.exit(codes.errors['unsupported_url_type'])
        elif os.path.isfile(source) and source.endswith('.tar.gz'):
            tmpdir = tempfile.mkdtemp()
            source = extract_source(source, tmpdir)
        elif os.path.isdir(source):
            source = os.path.expanduser(source)
        elif '==' in source:
            pass
        else:
            lgr.error('Path to source {0} does not exist.'.format(source))
            sys.exit(codes.errors['nonexistent_source_path'])
        lgr.debug('Source is: {0}'.format(source))
        return source

    def get_source_name_and_version(self, source):
        """Retrieves the source package's name and version.

        If the source is a path, the name and version will be retrieved
        by querying the setup.py file in the path.

        If the source is of format PACKAGE==VERSION, they will be used as
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
        # TODO: or just a package name...
        elif '==' in source:
            lgr.debug('Retrieving name and version...')
            self.name, self.version = source.split('==')
        lgr.info('Package name: {0}'.format(self.name))
        lgr.info('Package version: {0}'.format(self.version))
        return self.name, self.version

    def handle_output_file(self, archive, force):
        """Handles the output tar.

        removes the output file if required, else, notifies
        that it already exists.
        """
        if os.path.isfile(archive) and force:
            lgr.info('Removing previous archive...')
            os.remove(archive)
        if os.path.exists(archive):
            lgr.error('Destination archive already exists: {0}. You can use '
                      'the -f flag to overwrite.'.format(archive))
            sys.exit(codes.errors['archive_already_exists'])

    def handle_output_directory(self, wheels_path, force):
        if os.path.isdir(wheels_path):
            if force:
                shutil.rmtree(wheels_path)
            else:
                lgr.error('Directory {0} already exists. Please remove it and '
                          'run this again.'.format(wheels_path))
                sys.exit(codes.errors['directory_already_exists'])


@click.group()
def main():
    pass


@click.command()
@click.option('-s', '--source', required=True,
              help='Source URL, Path or Package name.')
@click.option('-r', '--with-requirements', required=False,
              help='Whether to also pack wheels from a requirements file.')
@click.option('-f', '--force', default=False, is_flag=True,
              help='Force overwriting existing output file.')
@click.option('--keep-wheels', default=False, is_flag=True,
              help='Keep wheels path after creation.')
@click.option('-x', '--exclude', default=None, multiple=True,
              help='Specific packages to exclude from the archive. '
                   'This argument can be provided multiple times.')
@click.option('-o', '--output-directory', default='.',
              help='Output directory for the archive.')
@click.option('--pyver', default=None, multiple=True,
              help='Explicit Python versions supported (e.g. py2, py3). '
                   'This argument can be provided multiple times.')
@click.option('--validate', default=False, is_flag=True,
              help='Runs a postcreation validation on the archive.')
@click.option('-a', '--wheel-args', required=False,
              help='Allows to pass additional arguments to `pip wheel`. '
                   '(e.g. --no-cache-dir -c constains.txt')
@click.option('-v', '--verbose', default=False, is_flag=True)
def create(source, with_requirements, force, keep_wheels, exclude,
           output_directory, pyver, validate, wheel_args, verbose):
    """Creates a Python package's wheel base archive.

    \b
    Example sources:
    - http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/
    master.tar.gz
    - ~/repos/cloudify-script-plugin
    - cloudify-script-plugin==1.2.1

    \b
    Note:
    - If source is URL, download and extract it and get its name and version
     from setup.py.
    - If source is a local path, get package name and version from setup.py.
    - If source is package_name==package_version, use them as name and version.
    """
    # TODO: Let the user provide supported Python versions.
    # TODO: Let the user provide supported Architectures.
    logger.configure()
    packager = Wagon(source, verbose)
    packager.create(
        with_requirements, force, keep_wheels, exclude, output_directory,
        pyver, validate, wheel_args)


@click.command()
@click.option('-s', '--source', required=True,
              help='Path or URL to source Wagon archive.')
@click.option('-e', '--virtualenv', default=None,
              help='Virtualenv to install in.')
@click.option('-r', '--requirements-file', required=False,
              help='A requirements file to install.')
@click.option('-u', '--upgrade', required=False, is_flag=True,
              help='Upgrades the package if it is already installed.')
@click.option('--ignore-platform', required=False, is_flag=True,
              help='Ignores supported platform check.')
@click.option('-a', '--install-args', required=False,
              help='Allows to pass additional arguments to `pip install`. '
                   '(e.g. -i my_pypi_index --retries 5')
@click.option('-v', '--verbose', default=False, is_flag=True)
def install(source, virtualenv, requirements_file, upgrade,
            ignore_platform, install_args, verbose):
    """Installs a Wagon archive.
    """
    logger.configure()
    installer = Wagon(source, verbose)
    installer.install(
        virtualenv, requirements_file, upgrade, ignore_platform, install_args)


@click.command()
@click.option('-s', '--source', required=True,
              help='Path or URL to source Wagon archive.')
@click.option('-v', '--verbose', default=False, is_flag=True)
def validate(source, verbose):
    """Validates an archive.

    This tests that all requires wheels exist, that the package
    is installable and that different metadata properties exist.
    """
    logger.configure()
    validator = Wagon(source, verbose)
    if not validator.validate():
        sys.exit('validation_failed')


@click.command()
@click.option('-s', '--source', required=True,
              help='Path or URL to source Wagon archive.')
@click.option('-v', '--verbose', default=False, is_flag=True)
def showmeta(source, verbose):
    """Prints out the metadata for an archive.
    """
    logger.configure()
    getter = Wagon(source, verbose)
    metadata = getter.get_metadata_from_archive()
    print(json.dumps(metadata, indent=4, sort_keys=True))


main.add_command(create)
main.add_command(install)
main.add_command(validate)
main.add_command(showmeta)
