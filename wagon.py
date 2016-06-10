########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import re
import sys
import time
import json
import shutil
import urllib
import urllib2
import tarfile
import zipfile
import logging
import platform
import tempfile
import subprocess
import pkg_resources
from threading import Thread
from contextlib import closing

import click
try:
    import virtualenv
except ImportError:
    pass
from wheel import pep425tags as wheel_tags


REQUIREMENT_FILE_NAMES = ['dev-requirements.txt', 'requirements.txt']
METADATA_FILE_NAME = 'package.json'
DEFAULT_WHEELS_PATH = 'wheels'

DEFAULT_INDEX_SOURCE_URL = 'https://pypi.python.org/pypi/{0}/json'
IS_VIRTUALENV = hasattr(sys, 'real_prefix')

PLATFORM = sys.platform
IS_WIN = (os.name == 'nt')
IS_DARWIN = (PLATFORM == 'darwin')
IS_LINUX = PLATFORM.startswith('linux')

PROCESS_POLLING_INTERVAL = 0.1


def setup_logger():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger('wagon')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = setup_logger()


class PipeReader(Thread):
    def __init__(self, fd, proc, logger, log_level):
        Thread.__init__(self)
        self.fd = fd
        self.proc = proc
        self.logger = logger
        self.log_level = log_level
        self.aggr = ''

    def run(self):
        while self.proc.poll() is None:
            output = self.fd.readline()
            if len(output) > 0:
                self.aggr += output
                self.logger.log(self.log_level, output.strip())
            else:
                time.sleep(PROCESS_POLLING_INTERVAL)


def run(cmd, suppress_errors=False, suppress_output=False):
    """Executes a command
    """
    logger.debug('Executing: {0}...'.format(cmd))
    pipe = subprocess.PIPE
    proc = subprocess.Popen(cmd, shell=True, stdout=pipe, stderr=pipe)

    stderr_log_level = logging.NOTSET if suppress_errors else logging.ERROR
    stdout_log_level = logging.NOTSET if suppress_errors else logging.DEBUG

    stdout_thread = PipeReader(proc.stdout, proc, logger, stdout_log_level)
    stderr_thread = PipeReader(proc.stderr, proc, logger, stderr_log_level)

    stdout_thread.start()
    stderr_thread.start()

    while proc.poll() is None:
        time.sleep(PROCESS_POLLING_INTERVAL)

    stdout_thread.join()
    stderr_thread.join()

    proc.aggr_stdout = stdout_thread.aggr
    proc.aggr_stderr = stderr_thread.aggr

    return proc


class WagonError(Exception):
    pass


def _construct_wheel_command(wheels_path='package',
                             excluded_packages=None,
                             wheel_args=None,
                             requirement_files=None,
                             package=None):
    pip_executable = _get_pip_path(os.environ.get('VIRTUAL_ENV'))

    wheel_cmd = [pip_executable, 'wheel']
    wheel_cmd.append('--wheel-dir={0}'.format(wheels_path))
    wheel_cmd.append('--find-links={0}'.format(wheels_path))
    if wheel_args:
        wheel_cmd.append(wheel_args)

    if requirement_files:
        for req_file in requirement_files:
            wheel_cmd.extend(['-r', req_file])
    if package:
        wheel_cmd.append(package)
    return ' '.join(wheel_cmd)


def _get_wheels(wheels_path, excluded_packages, package):
    wheels = _get_downloaded_wheels(wheels_path)
    excluded_packages = excluded_packages or []
    excluded_wheels = []
    for package in excluded_packages:
        wheel = _get_wheel_for_package(wheels_path, package)
        if wheel:
            excluded_wheels.append(wheel)
            wheels.remove(wheel)
            os.remove(os.path.join(wheels_path, wheel))
        else:
            logger.warn('Wheel not found for: {0}. Could not exclude.'.format(
                package))
    return wheels, excluded_wheels


def wheel(package,
          requirement_files=False,
          wheels_path='package',
          excluded_packages=None,
          wheel_args=None):
    logger.info('Downloading Wheels for {0}...'.format(package))

    if requirement_files:
        wheel_command = _construct_wheel_command(
            wheels_path,
            excluded_packages,
            wheel_args,
            requirement_files)
        process = run(wheel_command)
        if not process.returncode == 0:
            raise WagonError('Could not download wheels for: {0} ({1})'.format(
                requirement_files, process.aggr_stderr))

    wheel_command = _construct_wheel_command(
        wheels_path,
        excluded_packages,
        wheel_args,
        package=package)
    process = run(wheel_command)
    if not process.returncode == 0:
        raise WagonError('Could not download wheels for: {0} ({1})'.format(
            package, process.aggr_stderr))

    wheels, excluded_wheels = _get_wheels(
        wheels_path, excluded_packages, package)

    return wheels, excluded_wheels


def _get_wheel_for_package(wheels_path, package):
    for wheel in os.listdir(wheels_path):
        if wheel.startswith(package.replace('-', '_')):
            return wheel


def _construct_pip_command(package,
                           wheels_path,
                           virtualenv,
                           requirements_file=None,
                           upgrade=False,
                           install_args=None):
    pip_executable = _get_pip_path(virtualenv)

    pip_command = [pip_executable, 'install']
    if requirements_file:
        pip_command.extend(['-r', requirements_file])
    if install_args:
        pip_command.append(install_args)
    pip_command.append(package)
    pip_command.extend(
        ['--use-wheel', '--no-index', '--find-links', wheels_path])
    # pre allows installing both prereleases and regular releases depending
    # on the wheels provided.
    pip_command.append('--pre')
    if upgrade:
        pip_command.append('--upgrade')

    return ' '.join(pip_command)


def install_package(package,
                    wheels_path,
                    virtualenv=None,
                    requirements_file=None,
                    upgrade=False,
                    install_args=None):
    """This will install a Python package.

    Can specify a specific version.
    Can specify a prerelease.
    Can specify a virtualenv to install in.
    Can specify a list of paths or urls to requirement txt files.
    Can specify a local wheels_path to use for offline installation.
    Can request an upgrade.
    """
    logger.info('Installing {0}...'.format(package))
    if virtualenv and not os.path.isdir(virtualenv):
        raise WagonError('Virtualenv {0} does not exist'.format(virtualenv))

    pip_command = _construct_pip_command(
        package,
        wheels_path,
        virtualenv,
        requirements_file,
        upgrade,
        install_args)

    if IS_VIRTUALENV and not virtualenv:
        logger.info('Installing within current virtualenv: {0}...'.format(
            IS_VIRTUALENV))

    result = run(pip_command)
    if not result.returncode == 0:
        raise WagonError('Could not install package: {0} ({1})'.format(
            package, result.aggr_stderr))


def _get_downloaded_wheels(path):
    return \
        [filename for filename in os.listdir(path) if filename.endswith('whl')]


def _download_file(url, destination):
    logger.info('Downloading {0} to {1}...'.format(url, destination))
    final_url = urllib.urlopen(url).geturl()
    if final_url != url:
        logger.debug('Redirected to {0}'.format(final_url))
    f = urllib.URLopener()
    f.retrieve(final_url, destination)


def _zip(source, destination):
    logger.info('Creating zip archive: {0}...'.format(destination))
    with closing(zipfile.ZipFile(destination, 'w')) as zip:
        for root, _, files in os.walk(source):
            for filename in files:
                file_path = os.path.join(root, filename)
                source_dir = os.path.dirname(source)
                zip.write(file_path, os.path.relpath(file_path, source_dir))


def _unzip(archive, destination):
    logger.debug('Extracting zip {0} to {1}...'.format(archive, destination))
    with closing(zipfile.ZipFile(archive, 'r')) as zip:
        zip.extractall(destination)


def _tar(source, destination):
    logger.info('Creating tgz archive: {0}...'.format(destination))
    with closing(tarfile.open(destination, 'w:gz')) as tar:
        tar.add(source, arcname=os.path.basename(source))


def _untar(archive, destination):
    logger.debug('Extracting tgz {0} to {1}...'.format(archive, destination))
    with closing(tarfile.open(name=archive)) as tar:
        tar.extractall(path=destination, members=tar.getmembers())


def _get_wheel_tags(wheel_name):
    filename, _ = os.path.splitext(os.path.basename(wheel_name))
    return filename.split('-')


def _get_platform_from_wheel_name(wheel_name):
    """Extracts the platform of a wheel from its file name.
    """
    logger.error('AAAAAAA:{0}'.format(wheel_name))
    return _get_wheel_tags(wheel_name)[-1]


def _get_platform_for_set_of_wheels(wheels_path):
    """For any set of wheel files, extracts a single platform.

    Since a set of wheels created or downloaded on one machine can only
    be for a single platform, if any wheel in the set has a platform
    which is not `any`, it will be used. If a platform other than
    `any` was not found, `any` will be assumed.
    """
    for wheel in _get_downloaded_wheels(wheels_path):
        platform = _get_platform_from_wheel_name(
            os.path.join(wheels_path, wheel))
        if platform != 'any':
            return platform
    return 'any'


def _get_python_version():
    version = sys.version_info
    return 'py{0}{1}'.format(version[0], version[1])


def get_platform():
    return wheel_tags.get_platform()


def _get_os_properties():
    # TODO: replace with `distro`
    return platform.linux_distribution(full_distribution_name=False)


def _get_env_bin_path(env_path):
    """Returns the bin path for a virtualenv

    This provides a fallback for a situation in which you're trying
    to use the script and create a virtualenv from within
    a virtualenv in which virtualenv isn't installed and so
    is not importable.
    """
    if globals().get('virtualenv'):
        return virtualenv.path_locations(env_path)[3]
    else:
        return os.path.join(env_path, 'scripts' if IS_WIN else 'bin')


def _get_default_requirement_files(source):
    if os.path.isdir(source):
        return [os.path.join(source, f) for f in REQUIREMENT_FILE_NAMES
                if os.path.isfile(os.path.join(source, f))]


def _get_pip_path(virtualenv=None):
    pip = 'pip.exe' if IS_WIN else 'pip'
    if virtualenv:
        return os.path.join(_get_env_bin_path(virtualenv), pip)
    else:
        return os.path.join(
            os.path.dirname(sys.executable), 'scripts' if IS_WIN else '', pip)


def _check_installed(package, virtualenv):
    pip_executable = _get_pip_path(virtualenv)
    process = run('{0} freeze'.format(pip_executable), suppress_output=True)
    if re.search(r'{0}=='.format(package), process.aggr_stdout):
        logger.debug('Package {0} is installed in {1}'.format(
            package, virtualenv))
        return True
    logger.debug('Package {0} is not installed in {1}'.format(
        package, virtualenv))
    return False


def _make_virtualenv(virtualenv_dir):
    # TODO: allow to not pass a dir, in which case, this should create
    # a virtualenv in a tmp dir and return the path
    logger.debug('Creating Virtualenv {0}...'.format(virtualenv_dir))
    result = run('virtualenv {0}'.format(virtualenv_dir))
    if not result.returncode == 0:
        raise WagonError('Could not create virtualenv: {0} ({1})'.format(
            virtualenv_dir, result.aggr_stderr))


def _get_package_info_from_pypi(source):
    pypi_url = DEFAULT_INDEX_SOURCE_URL.format(source)
    logger.debug('Getting metadata for {0} from {1}...'.format(
        source, pypi_url))
    try:
        package_data = json.loads(urllib2.urlopen(pypi_url).read())
    except urllib2.HTTPError as ex:
        raise WagonError(
            "Failed to retrieve info for package. Request to {0} "
            "failed with HTTP Error: {1}".format(pypi_url, ex.code))
    return package_data['info']


def _get_wagon_version():
    return pkg_resources.get_distribution('wagon').version


def _set_python_versions(python_versions=None):
    if python_versions:
        return ['py{0}'.format(version) for version in python_versions]
    else:
        return [_get_python_version()]


def _get_name_and_version_from_setup(source_path):

    def get_arg(arg_type, setuppy_path):
        return run('{0} {1} --{2}'.format(
            sys.executable, setuppy_path, arg_type)).aggr_stdout.rstrip('\r\n')

    logger.debug('setup.py file found. Retrieving name and version...')
    setuppy_path = os.path.join(source_path, 'setup.py')
    package_name = get_arg('name', setuppy_path)
    package_version = get_arg('version', setuppy_path)
    return package_name, package_version


def _handle_output_file(filepath, force):
    if os.path.isfile(filepath) and force:
        logger.info('Removing previous archive...')
        os.remove(filepath)
    if os.path.isfile(filepath):
        raise WagonError(
            'Destination archive already exists: {0}. You can use '
            'the -f flag to overwrite.'.format(filepath))


def _generate_metadata_file(workdir,
                            archive_name,
                            platform,
                            python_versions,
                            package_name,
                            package_version,
                            package_source,
                            wheels,
                            excluded_wheels):
    """This generates a metadata file for the package.
    """
    logger.debug('Generating Metadata...')
    metadata = {
        'created_by_wagon_version': _get_wagon_version(),
        'archive_name': archive_name,
        'supported_platform': platform,
        'supported_python_versions': python_versions,
        'build_server_os_properties': {
            'distribution:': None,
            'distribution_version': None,
            'distribution_release': None,
        },
        'package_name': package_name,
        'package_version': package_version,
        'package_source': package_source,
        'wheels': wheels,
        'excluded_wheels': excluded_wheels
    }
    if IS_LINUX and platform != 'any':
        distro, version, release = _get_os_properties()
        metadata.update(
            {'build_server_os_properties': {
                'distribution': distro.lower(),
                'distribution_version': version.lower(),
                'distribution_release': release.lower()
            }})

    formatted_metadata = json.dumps(metadata, indent=4, sort_keys=True)
    logger.debug('Metadata is: {0}'.format(formatted_metadata))
    output_path = os.path.join(workdir, METADATA_FILE_NAME)
    with open(output_path, 'w') as f:
        logger.debug('Writing metadata to file: {0}'.format(output_path))
        f.write(formatted_metadata)


def _set_archive_name(package_name,
                      package_version,
                      python_versions,
                      platform):
    """Sets the format of the output archive file.

    We should aspire for the name of the archive to be
    as compatible as possible with the wheel naming convention
    described here:
    https://www.python.org/dev/peps/pep-0491/#file-name-convention,
    as we're basically providing a "wheel" of our package.
    """
    package_name = package_name.replace('-', '_')
    python_versions = '.'.join(python_versions)

    archive_name_tags = [
        package_name,
        package_version,
        python_versions,
        'none',
        platform,
        'none',
        'none'
    ]

    if IS_LINUX and platform != 'any':
        distro, _, release = _get_os_properties()
        # TODO: maybe replace `none` with `unknown`?
        # we found a linux distro but couldn't identify it.
        archive_name_tags[5] = distro or 'none'
        archive_name_tags[6] = release or 'none'

    archive_name = '{0}.wgn'.format('-'.join(archive_name_tags))
    return archive_name


def get_source_name_and_version(source):
    """Retrieves the source package's name and version.

    If the source is a path, the name and version will be retrieved
    by querying the setup.py file in the path.

    If the source is PACKAGE_NAME==PACKAGE_VERSION, they will be used as
    the name and version.

    If the source is PACKAGE_NAME, the version will be extracted from
    the wheel of the latest version.
    """
    if os.path.isfile(os.path.join(source, 'setup.py')):
        package_name, package_version = \
            _get_name_and_version_from_setup(source)
    # TODO: maybe we don't want to be that explicit and allow using >=
    # elif any(symbol in source for symbol in ['==', '>=', '<=']):
    elif '==' in source:
        base_name, package_version = source.split('==')
        package_name = _get_package_info_from_pypi(base_name)['name']
    else:
        package_info = _get_package_info_from_pypi(source)
        package_name = package_info['name']
        package_version = package_info['version']
    return package_name, package_version


def _create_wagon_archive(format, source_path, archive_path):
    if format == 'tar.gz':
        _tar(source_path, archive_path)
    elif format == 'zip':
        _zip(source_path, archive_path)
    else:
        raise WagonError(
            'Unsupported archive format to create: {0} '
            '(Must be one of [zip, tar.gz]).'.format(format))


def get_source(source):
    """Returns a pip-installable source

    If the source is a url to a package's tar file,
    this will download the source and extract it to a temporary directory.

    If the source is neither a url nor a local path, and is not provided
    as PACKAGE_NAME==PACKAGE_VERSION, the provided source string
    will be regarded as the source, which, by default, will assume
    that the string is a name of a package in PyPI.
    """
    def extract_source(source, destination):
        try:
            _untar(source, destination)
        except:
            try:
                _unzip(source, destination)
            except:
                raise WagonError(
                    'Failed to extract {0}. Please verify that the '
                    'provided file is a valid zip or tar.gz '
                    'archive'.format(source))
        source = os.path.join(
            destination, [d for d in os.walk(destination).next()[1]][0])
        return source

    remove_source_after_process = False

    logger.debug('Retrieving source...')
    if '://' in source:
        split = source.split('://')
        schema = split[0]
        if schema in ['http', 'https']:
            tmpdir = tempfile.mkdtemp()
            fd, tmpfile = tempfile.mkstemp()
            os.close(fd)
            try:
                remove_source_after_process = True
                _download_file(source, tmpfile)
                source = extract_source(tmpfile, tmpdir)
            finally:
                os.remove(tmpfile)
        else:
            raise WagonError('Source URL type {0} is not supported'.format(
                schema))
    elif os.path.isfile(source):
        remove_source_after_process = True
        tmpdir = tempfile.mkdtemp()
        source = extract_source(source, tmpdir)
    elif os.path.isdir(source):
        if not os.path.isfile(os.path.join(source, 'setup.py')):
            raise WagonError(
                'Source directory must contain a setup.py file')
        source = os.path.expanduser(source)
    elif '==' in source:
        base_name, version = source.split('==')
        source = _get_package_info_from_pypi(base_name)['name']
        source = '{0}=={1}'.format(source, version)
    else:
        source = _get_package_info_from_pypi(source)['name']
    logger.debug('Source is: {0}'.format(source))
    return source, remove_source_after_process


def _get_metadata(source_path):
    with open(os.path.join(source_path, METADATA_FILE_NAME)) as metadata_file:
        metadata = json.loads(metadata_file.read())
    return metadata


def create(source,
           with_requirements='',
           force=False,
           keep_wheels=False,
           excluded_packages=None,
           archive_destination_dir='.',
           python_versions=None,
           validate_archive=False,
           wheel_args='',
           format='tar.gz',
           verbose=False):
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
    logger.info('Creating archive for {0}...'.format(source))
    original_source = source
    source, remove_source_after_process = get_source(source)
    package_name, package_version = get_source_name_and_version(source)

    excluded_packages = excluded_packages or []
    if excluded_packages:
        logger.warn('Note that excluding packages may make the archive '
                    'non-installable.')
    if package_name in excluded_packages:
        raise WagonError(
            'You cannot exclude the package you are trying to wheel.')

    tempdir = tempfile.mkdtemp()
    workdir = os.path.join(tempdir, package_name)
    wheels_path = os.path.join(workdir, DEFAULT_WHEELS_PATH)

    if with_requirements:
        with_requirements = _get_default_requirement_files(source)

    try:
        wheels, excluded_wheels = wheel(
            source, with_requirements, wheels_path, excluded_packages,
            wheel_args)
    finally:
        if remove_source_after_process:
            shutil.rmtree(source, ignore_errors=True)

    platform = _get_platform_for_set_of_wheels(wheels_path)
    logger.debug('Platform is: {0}'.format(platform))
    python_versions = _set_python_versions(python_versions)

    if not os.path.isdir(archive_destination_dir):
        os.makedirs(archive_destination_dir)
    archive_name = _set_archive_name(
        package_name, package_version, python_versions, platform)
    archive_path = os.path.join(archive_destination_dir, archive_name)

    _handle_output_file(archive_path, force)
    _generate_metadata_file(
        workdir,
        archive_name,
        platform,
        python_versions,
        package_name,
        package_version,
        original_source,
        wheels,
        excluded_wheels)

    _create_wagon_archive(format, workdir, archive_path)
    if not keep_wheels:
        logger.debug('Cleaning up...')
        shutil.rmtree(workdir, ignore_errors=True)

    if validate_archive:
        validate(archive_path, verbose)
    logger.info('Process complete!')
    return archive_path


def install(source,
            virtualenv='',
            requirements_file='',
            upgrade=False,
            ignore_platform=False,
            install_args='',
            verbose=False):
    """Installs a Wagon archive.

    This can install in a provided `virtualenv` or in the current
    virtualenv in case one is currently active.

    `upgrade` is merely pip's upgrade.

    `ignore_platform` will allow to ignore the platform check, meaning
    that if an archive was created for a specific platform (e.g. win32),
    and the current platform is different, it will still attempt to
    install it.
    """
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    logger.info('Installing {0}'.format(source))
    # TODO: remove source after process?
    source, _ = get_source(source)
    metadata = _get_metadata(source)

    try:
        supported_platform = metadata['supported_platform']
        if not ignore_platform and supported_platform != 'any':
            logger.debug('Validating Platform {0} is supported...'.format(
                supported_platform))
            machine_platform = get_platform()
            if machine_platform != supported_platform:
                raise WagonError(
                    'Platform unsupported for package ({0}).'.format(
                        machine_platform))

        wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
        install_package(
            metadata['package_name'],
            wheels_path,
            virtualenv,
            requirements_file,
            upgrade,
            install_args)
    finally:
        shutil.rmtree(source)


def validate(source, verbose=False):
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
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    logger.info('Validating {0}'.format(source))
    original_source = source
    source, _ = get_source(source)
    metadata = _get_metadata(source)

    wheels_path = os.path.join(source, DEFAULT_WHEELS_PATH)
    validation_errors = []

    logger.debug('Verifying that all required files exist...')
    for wheel in metadata['wheels']:
        if not os.path.isfile(os.path.join(wheels_path, wheel)):
            validation_errors.append(
                '{0} is missing from the archive'.format(wheel))

    logger.debug('Testing package installation...')
    excluded_wheels = metadata.get('excluded_wheels')
    if excluded_wheels:
        for wheel in excluded_wheels:
            logger.warn(
                'Wheel {0} is excluded from the archive and is '
                'possibly required for installation.'.format(wheel))
    tmpenv = tempfile.mkdtemp()
    try:
        _make_virtualenv(tmpenv)
        install(source=original_source, virtualenv=tmpenv, verbose=verbose)
        if not _check_installed(metadata['package_name'], tmpenv):
            validation_errors.append(
                '{0} failed to install (Reason unknown)'.format(
                    metadata['package_name']))
    finally:
        shutil.rmtree(tmpenv)
        shutil.rmtree(source)

    if validation_errors:
        logger.info('Validation failed!')
        for error in validation_errors:
            logger.info(error)
        logger.info('Source can be found at: {0}'.format(source))
    else:
        logger.info('Validation Passed! (Cleaning up temporary files).')
        shutil.rmtree(os.path.dirname(source))
    return validation_errors


def show(source, verbose=False):
    """Merely returns the metadata from the provided archive.
    """
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    logger.debug('Retrieving Metadata for: {0}'.format(source))
    source, _ = get_source(source)
    metadata = _get_metadata(source)
    shutil.rmtree(source)
    return metadata


@click.group()
def main():
    pass


@main.command(name='create')
@click.argument('source', required=True)
@click.option('-r',
              '--with-requirements',
              required=False,
              is_flag=True,
              help='Whether to also pack wheels from a requirements file')
@click.option('-t',
              '--format',
              required=False,
              default='tar.gz',
              type=click.Choice(['tar.gz', 'zip']),
              help='Which file format to generate')
@click.option('-f',
              '--force',
              default=False,
              is_flag=True,
              help='Force overwriting existing output file')
@click.option('--keep-wheels',
              default=False,
              is_flag=True,
              help='Keep wheels path after creation')
@click.option('-x',
              '--exclude',
              default=None,
              multiple=True,
              help='Specific packages to exclude from the archive. '
                   'This argument can be provided multiple times')
@click.option('-o',
              '--output-directory',
              default='.',
              help='Output directory for the archive')
@click.option('--pyver',
              default=None,
              multiple=True,
              help='Explicit Python versions supported (e.g. py2, py3). '
                   'This argument can be provided multiple times')
@click.option('--validate',
              default=False,
              is_flag=True,
              help='Runs a postcreation validation on the archive')
@click.option('-a',
              '--wheel-args',
              required=False,
              help='Allows to pass additional arguments to `pip wheel`. '
                   '(e.g. --no-cache-dir -c constains.txt')
@click.option('-v', '--verbose', default=False, is_flag=True)
def create_wagon(source,
                 with_requirements,
                 format,
                 force,
                 keep_wheels,
                 exclude,
                 output_directory,
                 pyver,
                 validate,
                 wheel_args,
                 verbose):
    r"""Creates a wagon from pip-installable sources

    \b
    Example sources:
    - http://github.com/cloudify-cosmo/cloudify-script-plugin/archive/
    master.tar.gz
    - /my/python/package/dir
    - my-pypi-package==1.2.1
    - my-other-pypi-package (will use latest version found in PyPI)
    \b
    """
    try:
        create(
            source=source,
            with_requirements=with_requirements,
            force=force,
            keep_wheels=keep_wheels,
            excluded_packages=exclude,
            archive_destination_dir=output_directory,
            python_versions=pyver,
            validate_archive=validate,
            wheel_args=wheel_args,
            format=format,
            verbose=verbose)
    except WagonError as ex:
        logger.error(ex)
        sys.exit(1)


@main.command(name='install')
@click.argument('source', required=True)
@click.option('-e',
              '--virtualenv',
              default=None,
              help='Virtualenv to install in')
@click.option('-r',
              '--requirements-file',
              required=False,
              help='A requirements file to install')
@click.option('-u',
              '--upgrade',
              required=False,
              is_flag=True,
              help='Upgrades the package if it is already installed')
@click.option('--ignore-platform',
              required=False,
              is_flag=True,
              help='Ignores supported platform check')
@click.option('-a',
              '--install-args',
              required=False,
              help='Allows to pass additional arguments to `pip install`. '
                   '(e.g. -i my_pypi_index --retries 5')
@click.option('-v', '--verbose', default=False, is_flag=True)
def install_wagon(source,
                  virtualenv,
                  requirements_file,
                  upgrade,
                  ignore_platform,
                  install_args,
                  verbose):
    """Installs a wagon
    """
    try:
        install(
            source=source,
            virtualenv=virtualenv,
            requirements_file=requirements_file,
            upgrade=upgrade,
            ignore_platform=ignore_platform,
            install_args=install_args,
            verbose=verbose)
    except WagonError as ex:
        logger.error(ex)
        sys.exit(1)


@main.command(name='validate')
@click.argument('source', required=True)
@click.option('-v', '--verbose', default=False, is_flag=True)
def validate_wagon(source, verbose):
    """Validates that an archive is a valid wagon

    This validates that the archive's structure is one of a valid wagon
    and that all requires wheels exist, after which it creates a virtualenv
    and installs the package into it.
    """
    try:
        if len(validate(source, verbose)) > 0:
            sys.exit(1)
    except WagonError as ex:
        logger.error(ex)
        sys.exit(1)


@main.command(name='show')
@click.argument('source', required=True)
@click.option('-v', '--verbose', default=False, is_flag=True)
def show_wagon(source, verbose):
    """Prints out the metadata for a wagon
    """
    try:
        metadata = show(source, verbose)
        print(json.dumps(metadata, indent=4, sort_keys=True))
    except WagonError as ex:
        logger.error(ex)
        sys.exit(1)
