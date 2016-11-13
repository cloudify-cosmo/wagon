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

from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import time
import json
import shutil
import tarfile
import zipfile
import logging
import argparse
import platform
import tempfile
import subprocess
import pkg_resources
from io import StringIO
from threading import Thread
from contextlib import closing

try:
    import urllib.error
    from urllib.request import urlopen
    from urllib.request import URLopener
except ImportError:
    import urllib
    from urllib import urlopen
    from urllib import URLopener

try:
    import virtualenv
except ImportError:
    pass
from wheel import pep425tags


DESCRIPTION = \
    '''Create and install wheel based packages with their dependencies'''


IS_PY3 = sys.version_info[:2] > (2, 7)

METADATA_FILE_NAME = 'package.json'
DEFAULT_WHEELS_PATH = 'wheels'

DEFAULT_INDEX_SOURCE_URL_TEMPLATE = 'https://pypi.python.org/pypi/{0}/json'
IS_VIRTUALENV = hasattr(sys, 'real_prefix')

PLATFORM = sys.platform
IS_WIN = (os.name == 'nt')
IS_DARWIN = (PLATFORM == 'darwin')
IS_LINUX = PLATFORM.startswith('linux')

ALL_PLATFORMS_TAG = 'any'

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
    def __init__(self, fd, process, logger, log_level):
        Thread.__init__(self)
        self.fd = fd
        self.process = process
        self.logger = logger
        self.log_level = log_level
        self._aggr = StringIO()
        self.aggr = ''

    def run(self):
        while self.process.poll() is None:
            output = self.fd.readline().strip().decode('utf-8')
            if len(output) > 0:
                self._aggr.write(output)
                self.logger.log(self.log_level, output)
            else:
                time.sleep(PROCESS_POLLING_INTERVAL)
        self.aggr = self._aggr.getvalue()


def _run(cmd, suppress_errors=False, suppress_output=False):
    """Executes a command
    """
    logger.debug('Executing: {0}...'.format(cmd))
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stderr_log_level = logging.NOTSET if suppress_errors else logging.ERROR
    stdout_log_level = logging.NOTSET if suppress_output else logging.DEBUG

    stdout_thread = PipeReader(
        process.stdout, process, logger, stdout_log_level)
    stderr_thread = PipeReader(
        process.stderr, process, logger, stderr_log_level)

    stdout_thread.start()
    stderr_thread.start()

    while process.poll() is None:
        time.sleep(PROCESS_POLLING_INTERVAL)

    stdout_thread.join()
    stderr_thread.join()

    process.aggr_stdout = stdout_thread.aggr
    process.aggr_stderr = stderr_thread.aggr

    return process


class WagonError(Exception):
    pass


def _construct_wheel_command(wheels_path='package',
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


def wheel(package,
          requirement_files=False,
          wheels_path='package',
          wheel_args=None):
    logger.info('Downloading Wheels for {0}...'.format(package))

    if requirement_files:
        wheel_command = _construct_wheel_command(
            wheels_path,
            wheel_args,
            requirement_files)
        process = _run(wheel_command)
        if not process.returncode == 0:
            raise WagonError('Could not download wheels for: {0} ({1})'.format(
                requirement_files, process.aggr_stderr))

    wheel_command = _construct_wheel_command(
        wheels_path,
        wheel_args,
        package=package)
    process = _run(wheel_command)
    if not process.returncode == 0:
        raise WagonError('Could not download wheels for: {0} ({1})'.format(
            package, process.aggr_stderr))

    wheels = _get_downloaded_wheels(wheels_path)

    return wheels


def _construct_pip_command(package,
                           wheels_path,
                           virtualenv,
                           requirement_files=None,
                           upgrade=False,
                           install_args=None):
    requirement_files = requirement_files or []

    pip_executable = _get_pip_path(virtualenv)

    pip_command = [pip_executable, 'install']
    for req_file in requirement_files:
        pip_command.extend(['-r', req_file])
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
                    requirement_files=None,
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
    requirement_files = requirement_files or []

    logger.info('Installing {0}...'.format(package))
    if virtualenv and not os.path.isdir(virtualenv):
        raise WagonError('Virtualenv {0} does not exist'.format(virtualenv))

    pip_command = _construct_pip_command(
        package,
        wheels_path,
        virtualenv,
        requirement_files,
        upgrade,
        install_args)

    if IS_VIRTUALENV and not virtualenv:
        logger.info('Installing within current virtualenv: {0}...'.format(
            IS_VIRTUALENV))

    result = _run(pip_command)
    if not result.returncode == 0:
        raise WagonError('Could not install package: {0} ({1})'.format(
            package, result.aggr_stderr))


def _get_downloaded_wheels(path):
    return [filename for filename in os.listdir(path)
            if os.path.splitext(filename)[1].lower() == '.whl']


def _open_url(url):
    if IS_PY3:
        try:
            response = urlopen(url)
            # Sometimes bytes are returned here and sometimes strings.
            try:
                response.text = response.read().decode('utf-8')
            except UnicodeDecodeError:
                response.text = response.read()
            response.code = 200
        except urllib.error.HTTPError as ex:
            response = type('obj', (object,), {'code': ex.code})
    else:
        response = urlopen(url)
        response.text = response.read()

    return response


def _download_file(url, destination):
    logger.info('Downloading {0} to {1}...'.format(url, destination))

    response = _open_url(url)

    if not response.code == 200:
        raise WagonError(
            "Failed to download file. Request to {0} "
            "failed with HTTP Error: {1}".format(url, response.code))
    final_url = response.geturl()
    if final_url != url:
        logger.debug('Redirected to {0}'.format(final_url))
    f = URLopener()
    f.retrieve(final_url, destination)


def _http_request(url):
    response = _open_url(url)

    if response.code == 200:
        return response.text
    else:
        # TODO: Fix message. Not generic enough
        raise WagonError(
            "Failed to retrieve info for package. Request to {0} "
            "failed with HTTP Error: {1}".format(url, response.code))


def _zip(source, destination):
    logger.info('Creating zip archive: {0}...'.format(destination))
    with closing(zipfile.ZipFile(destination, 'w')) as zip_file:
        for root, _, files in os.walk(source):
            for filename in files:
                file_path = os.path.join(root, filename)
                source_dir = os.path.dirname(source)
                zip_file.write(
                    file_path, os.path.relpath(file_path, source_dir))


def _unzip(archive, destination):
    logger.debug('Extracting zip {0} to {1}...'.format(archive, destination))
    with closing(zipfile.ZipFile(archive, 'r')) as zip_file:
        zip_file.extractall(destination)


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
        if platform != ALL_PLATFORMS_TAG:
            return platform
    return ALL_PLATFORMS_TAG


def _get_python_version():
    version = sys.version_info
    return 'py{0}{1}'.format(version[0], version[1])


def get_platform():
    return pep425tags.get_platform()


def _get_os_properties():
    # TODO: replace with `distro`
    return platform.linux_distribution(full_distribution_name=False)


def _get_env_bin_path(env_path):
    """Return the bin path for a virtualenv

    This provides a fallback for a situation in which you're trying
    to use the script and create a virtualenv from within
    a virtualenv in which virtualenv isn't installed and so
    is not importable.
    """
    if globals().get('virtualenv'):
        return virtualenv.path_locations(env_path)[3]
    else:
        return os.path.join(env_path, 'scripts' if IS_WIN else 'bin')


def _get_pip_path(virtualenv=None):
    pip = 'pip.exe' if IS_WIN else 'pip'
    if virtualenv:
        return os.path.join(_get_env_bin_path(virtualenv), pip)
    else:
        return os.path.join(
            os.path.dirname(sys.executable), 'scripts' if IS_WIN else '', pip)


def _check_installed(package, virtualenv):
    pip_executable = _get_pip_path(virtualenv)
    process = _run('{0} freeze'.format(pip_executable), suppress_output=True)
    if '{0}=='.format(package) in process.aggr_stdout:
        logger.debug('Package {0} is installed in {1}'.format(
            package, virtualenv))
        return True
    logger.debug('Package {0} is not installed in {1}'.format(
        package, virtualenv))
    return False


def _make_virtualenv():
    virtualenv_dir = tempfile.mkdtemp()
    logger.debug('Creating Virtualenv {0}...'.format(virtualenv_dir))
    _run('virtualenv {0}'.format(virtualenv_dir))
    return virtualenv_dir


def _get_package_info_from_pypi(source):
    pypi_url = DEFAULT_INDEX_SOURCE_URL_TEMPLATE.format(source)
    logger.debug('Getting metadata for {0} from {1}...'.format(
        source, pypi_url))
    package_data = json.loads(_http_request(pypi_url))
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
        return _run('{0} {1} --{2}'.format(
            sys.executable, setuppy_path, arg_type)).aggr_stdout.strip()

    logger.debug('setup.py file found. Retrieving name and version...')
    setuppy_path = os.path.join(source_path, 'setup.py')
    package_name = get_arg('name', setuppy_path)
    package_version = get_arg('version', setuppy_path)
    return package_name, package_version


def _handle_output_file(filepath, force):
    if os.path.isfile(filepath):
        if force:
            logger.info('Removing previous archive...')
            os.remove(filepath)
        else:
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
                            wheels):
    """Generate a metadata file for the package.
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
    }
    if IS_LINUX and platform != ALL_PLATFORMS_TAG:
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
    """Set the format of the output archive file.

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

    if IS_LINUX and platform != ALL_PLATFORMS_TAG:
        distro, _, release = _get_os_properties()
        # TODO: maybe replace `none` with `unknown`?
        # we found a linux distro but couldn't identify it.
        archive_name_tags[5] = distro or 'none'
        archive_name_tags[6] = release or 'none'

    archive_name = '{0}.wgn'.format('-'.join(archive_name_tags))
    return archive_name


def get_source_name_and_version(source):
    """Retrieve the source package's name and version.

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
    if format.lower() == 'tar.gz':
        _tar(source_path, archive_path)
    elif format.lower() == 'zip':
        _zip(source_path, archive_path)
    else:
        raise WagonError(
            'Unsupported archive format to create: {0} '
            '(Must be one of [zip, tar.gz]).'.format(format.lower()))


def get_source(source):
    """Return a pip-installable source

    If the source is a url to a package's tar file,
    this will download the source and extract it to a temporary directory.

    If the source is neither a url nor a local path, and is not provided
    as PACKAGE_NAME==PACKAGE_VERSION, the provided source string
    will be regarded as the source, which, by default, will assume
    that the string is a name of a package in PyPI.
    """
    def extract_source(source, destination):
        if tarfile.is_tarfile(source):
            _untar(source, destination)
        elif zipfile.is_zipfile(source):
            _unzip(source, destination)
        else:
            raise WagonError(
                'Failed to extract {0}. Please verify that the '
                'provided file is a valid zip or tar.gz '
                'archive'.format(source))

        source = os.path.join(
            destination, [d for d in next(os.walk(destination))[1]][0])
        return source

    logger.debug('Retrieving source...')
    if '://' in source:
        split = source.split('://')
        schema = split[0]
        if schema in ['file', 'http', 'https']:
            tmpdir = tempfile.mkdtemp()
            fd, tmpfile = tempfile.mkstemp()
            os.close(fd)
            try:
                _download_file(source, tmpfile)
                source = extract_source(tmpfile, tmpdir)
            finally:
                os.remove(tmpfile)
        else:
            raise WagonError('Source URL type {0} is not supported'.format(
                schema))
    elif os.path.isfile(source):
        tmpdir = tempfile.mkdtemp()
        source = extract_source(source, tmpdir)
    elif os.path.isdir(os.path.expanduser(source)):
        source = os.path.expanduser(source)
    elif '==' in source:
        base_name, version = source.split('==')
        source = _get_package_info_from_pypi(base_name)['name']
        source = '{0}=={1}'.format(source, version)
    else:
        source = _get_package_info_from_pypi(source)['name']
    logger.debug('Source is: {0}'.format(source))
    return source


def _get_metadata(source_path):
    with open(os.path.join(source_path, METADATA_FILE_NAME)) as metadata_file:
        metadata = json.loads(metadata_file.read())
    return metadata


def _set_verbosity(verbose):
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def create(source,
           requirement_files='',
           force=False,
           keep_wheels=False,
           archive_destination_dir='.',
           python_versions=None,
           validate_archive=False,
           wheel_args='',
           format='tar.gz',
           verbose=False):
    """Create a Wagon archive and returns its path.

    This currently only creates tar.gz archives. The `install`
    method assumes tar.gz when installing on Windows as well.

    Package name and version are extracted from the setup.py file
    of the `source` or from the PACKAGE_NAME==PACKAGE_VERSION if the source
    is a PyPI package.

    Supported `python_versions` must be in the format e.g [33, 27, 2, 3]..

    `force` will remove any excess dirs or archives before creation.

    `requirement_files` can be either a link/local path to a
    requirements.txt file or just `.`, in which case requirement files
    will be automatically extracted from either the GitHub archive URL
    or the local path provided provided in `source`.
    """
    _set_verbosity(verbose)

    logger.info('Creating archive for {0}...'.format(source))
    processed_source = get_source(source)
    if os.path.isdir(processed_source) and not \
            os.path.isfile(os.path.join(processed_source, 'setup.py')):
        raise WagonError(
            'Source directory must contain a setup.py file')
    package_name, package_version = get_source_name_and_version(
        processed_source)

    tempdir = tempfile.mkdtemp()
    workdir = os.path.join(tempdir, package_name)
    wheels_path = os.path.join(workdir, DEFAULT_WHEELS_PATH)

    try:
        wheels = wheel(
            processed_source,
            requirement_files,
            wheels_path,
            wheel_args)
    finally:
        if processed_source != source:
            shutil.rmtree(processed_source, ignore_errors=True)

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
        source,
        wheels)

    _create_wagon_archive(format, workdir, archive_path)
    if not keep_wheels:
        logger.debug('Removing work directory...')
        shutil.rmtree(tempdir, ignore_errors=True)

    if validate_archive:
        validate(archive_path, verbose)
    logger.info('Wagon created successfully at: {0}'.format(archive_path))
    return archive_path


def install(source,
            virtualenv='',
            requirement_files=None,
            upgrade=False,
            ignore_platform=False,
            install_args='',
            verbose=False):
    """Install a Wagon archive.

    This can install in a provided `virtualenv` or in the current
    virtualenv in case one is currently active.

    `upgrade` is merely pip's upgrade.

    `ignore_platform` will allow to ignore the platform check, meaning
    that if an archive was created for a specific platform (e.g. win32),
    and the current platform is different, it will still attempt to
    install it.
    """
    _set_verbosity(verbose)

    requirement_files = requirement_files or []

    logger.info('Installing {0}'.format(source))
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)

    try:
        supported_platform = metadata['supported_platform']
        if not ignore_platform and supported_platform != ALL_PLATFORMS_TAG:
            logger.debug('Validating Platform {0} is supported...'.format(
                supported_platform))
            machine_platform = get_platform()
            if machine_platform != supported_platform:
                raise WagonError(
                    'Platform unsupported for package ({0}).'.format(
                        machine_platform))

        wheels_path = os.path.join(processed_source, DEFAULT_WHEELS_PATH)
        install_package(
            metadata['package_name'],
            wheels_path,
            virtualenv,
            requirement_files,
            upgrade,
            install_args)
    finally:
        if processed_source != source:
            shutil.rmtree(processed_source)


def validate(source, verbose=False):
    """Validate a Wagon archive. Return True if succeeds, False otherwise.
    It also prints a list of all validation errors.

    This will test that some of the metadata is solid, that
    the required wheels are present within the archives and that
    the package is installable.

    Note that if the metadata file is corrupted, validation
    of the required wheels will be corrupted as well, since validation
    checks that the required wheels exist vs. the list of wheels
    supplied in the `wheels` key.
    """
    _set_verbosity(verbose)

    logger.info('Validating {0}'.format(source))
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)

    wheels_path = os.path.join(processed_source, DEFAULT_WHEELS_PATH)
    validation_errors = []

    logger.debug('Verifying that all required files exist...')
    for wheel in metadata['wheels']:
        if not os.path.isfile(os.path.join(wheels_path, wheel)):
            validation_errors.append(
                '{0} is missing from the archive'.format(wheel))

    logger.debug('Testing package installation...')
    tmpenv = _make_virtualenv()
    try:
        install(source=processed_source, virtualenv=tmpenv, verbose=verbose)
        if not _check_installed(metadata['package_name'], tmpenv):
            validation_errors.append(
                '{0} failed to install (Reason unknown)'.format(
                    metadata['package_name']))
    finally:
        shutil.rmtree(tmpenv)

    if validation_errors:
        logger.info('Validation failed!')
        for error in validation_errors:
            logger.info(error)
        logger.info('Source can be found at: {0}'.format(processed_source))
    else:
        logger.info('Validation Passed!')
        if processed_source != source:
            shutil.rmtree(processed_source)
    return validation_errors


def show(source, verbose=False):
    """Merely returns the metadata for the provided archive.
    """
    _set_verbosity(verbose)

    logger.info('Retrieving Metadata for: {0}'.format(source))
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)
    shutil.rmtree(processed_source)
    return metadata


def _create_wagon(args):
    try:
        create(
            source=args.SOURCE,
            requirement_files=args.requirements_file,
            force=args.force,
            keep_wheels=args.keep_wheels,
            archive_destination_dir=args.output_directory,
            python_versions=args.pyver,
            validate_archive=args.validate,
            wheel_args=args.wheel_args,
            format=args.format,
            verbose=args.verbose)
    except WagonError as ex:
        sys.exit(ex)


def _install_wagon(args):
    try:
        install(
            source=args.SOURCE,
            virtualenv=args.virtualenv,
            requirement_files=args.requirements_file,
            upgrade=args.upgrade,
            ignore_platform=args.ignore_platform,
            install_args=args.install_args,
            verbose=args.verbose)
    except WagonError as ex:
        sys.exit(ex)


def _validate_wagon(args):
    try:
        if len(validate(args.SOURCE, args.verbose)) > 0:
            sys.exit(1)
    except WagonError as ex:
        sys.exit(ex)


def _show_wagon(args):
    try:
        metadata = show(args.SOURCE, args.verbose)
        print(json.dumps(metadata, indent=4, sort_keys=True))
    except WagonError as ex:
        sys.exit(ex)


def _add_verbose_argument(parser):
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Set verbose logging level')
    return parser


def _add_common(parser, func):
    parser.add_argument('SOURCE')
    parser = _add_verbose_argument(parser)
    parser.set_defaults(func=func)
    return parser


def _add_create_command(parser):
    command = parser.add_parser(
        'create',
        help='Create a wagon from pip-installable sources')

    command.add_argument(
        '-r',
        '--requirements-file',
        action='append',
        help='Whether to also pack wheels from a requirements file')
    command.add_argument(
        '-t',
        '--format',
        required=False,
        default='tar.gz',
        choices=(['tar.gz', 'zip']),
        help='Which file format to generate')
    command.add_argument(
        '-f',
        '--force',
        default=False,
        action='store_true',
        help='Force overwriting existing output file')
    command.add_argument(
        '--keep-wheels',
        default=False,
        action='store_true',
        help='Keep wheels path after creation')
    command.add_argument(
        '-o',
        '--output-directory',
        default='.',
        help='Output directory for the archive')
    command.add_argument(
        '--pyver',
        default=None,
        action='append',
        help='Explicit Python versions supported (e.g. py2, py3). '
             'This argument can be provided multiple times')
    command.add_argument(
        '--validate',
        default=False,
        action='store_true',
        help='Runs a postcreation validation on the archive')
    command.add_argument(
        '-a',
        '--wheel-args',
        required=False,
        help='Allows to pass additional arguments to `pip wheel`. '
             '(e.g. --no-cache-dir -c constains.txt)')

    _add_common(command, func=_create_wagon)
    return parser


def _add_install_command(parser):
    command = parser.add_parser(
        'install',
        help='Install a Wagon')

    command.add_argument(
        '-e',
        '--virtualenv',
        default=None,
        help='Virtualenv to install in')
    command.add_argument(
        '-r',
        '--requirements-file',
        required=False,
        action='append',
        help='A requirements file to install. '
        'This flag can be used multiple times')
    command.add_argument(
        '-u',
        '--upgrade',
        required=False,
        action='store_true',
        help='Upgrades the package if it is already installed')
    command.add_argument(
        '--ignore-platform',
        required=False,
        action='store_true',
        help='Ignores supported platform check')
    command.add_argument(
        '-a',
        '--install-args',
        required=False,
        help='Allows to pass additional arguments to `pip install`. '
             '(e.g. -i my_pypi_index --retries 5')

    _add_common(command, func=_install_wagon)
    return parser


def _add_validate_command(parser):
    command = parser.add_parser(
        'validate',
        help=("Validate an archive\nThis validates that the archive's\n"
              "structure is one of a valid wagon and that all requires\n"
              "wheels exist, after which it creates a virtualenv\n"
              "and installs the package into it."))

    _add_common(command, func=_validate_wagon)
    return parser


def _add_show_command(parser):
    command = parser.add_parser(
        'show',
        help='Print out the metadata of a wagon')

    _add_common(command, func=_show_wagon)
    return parser


def parse_args():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter)
    parser = _add_verbose_argument(parser)

    subparsers = parser.add_subparsers()
    subparsers = _add_create_command(subparsers)
    subparsers = _add_install_command(subparsers)
    subparsers = _add_validate_command(subparsers)
    subparsers = _add_show_command(subparsers)

    return parser.parse_args()


def main():
    args = parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
