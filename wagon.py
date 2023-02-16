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

import os
import sys
import time
import json
import shlex
import shutil
import tarfile
import zipfile
import logging
import argparse
import tempfile
import subprocess
import pkg_resources
import distutils.util
import venv
from io import StringIO
from threading import Thread
from contextlib import closing
from distutils.spawn import find_executable
from pkginfo import Wheel

try:
    import urllib.error
    from urllib.request import urlopen
    from urllib.request import URLopener
except ImportError:
    import urllib
    from urllib import urlopen
    from urllib import URLopener

try:
    from distro import linux_distribution
except ImportError:
    try:
        from platform import linux_distribution
    except ImportError:
        linux_distribution = None


DESCRIPTION = \
    '''Create and install wheel based packages with their dependencies'''

METADATA_FILE_NAME = 'package.json'
DEFAULT_WHEELS_PATH = 'wheels'
DEFAULT_FILES_PATH = 'files'

DEFAULT_INDEX_SOURCE_URL_TEMPLATE = 'https://pypi.python.org/pypi/{0}/json'
IS_VIRTUALENV = sys.prefix != sys.base_prefix

PLATFORM = sys.platform
IS_WIN = (os.name == 'nt')
IS_DARWIN = (PLATFORM == 'darwin')
IS_LINUX = PLATFORM.startswith('linux')

ALL_PLATFORMS_TAG = 'any'

PROCESS_POLLING_INTERVAL = 0.1


def setup_logger():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger('wagon')
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


logger = setup_logger()


def set_verbose():
    # TODO: This is a very naive implementation. We should really
    # use a logging configuration based on different levels of
    # verbosity.
    # The default level should be something in the middle and
    # different levels of `--verbose` and `--quiet` flags should be
    # supported.
    global verbose
    verbose = True


def is_verbose():
    global verbose
    try:
        return verbose
    except NameError:
        verbose = False
        return verbose


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
    """Execute a command
    """
    if is_verbose():
        logger.debug('Executing: %r', cmd)
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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
                             package=None, pip_path=None):
    pip = [pip_path] if pip_path else _pip()
    wheel_cmd = pip + [
        'wheel',
        '--wheel-dir', wheels_path,
        '--find-links', wheels_path
    ]
    if wheel_args:
        if not isinstance(wheel_args, list):
            wheel_args = shlex.split(wheel_args, posix=not IS_WIN)
        wheel_cmd += wheel_args

    if requirement_files:
        for req_file in requirement_files:
            wheel_cmd += ['-r', req_file]

    if package:
        wheel_cmd.append(package)
    return wheel_cmd


def wheel(package,
          requirement_files=None,
          wheels_path='package',
          wheel_args=None,
          pip_path=None):
    logger.info('Downloading Wheels for %s...', package)

    if requirement_files:
        wheel_command = _construct_wheel_command(
            wheels_path,
            wheel_args,
            requirement_files,
            pip_path=pip_path)
        process = _run(wheel_command)
        if not process.returncode == 0:
            raise WagonError('Failed to download wheels for: {0}'.format(
                requirement_files))

    wheel_command = _construct_wheel_command(
        wheels_path,
        wheel_args,
        package=package,
        pip_path=pip_path)
    process = _run(wheel_command)
    if not process.returncode == 0:
        raise WagonError(
            'Failed to download wheels for: {0}'.format(package))

    wheels = _get_downloaded_wheels(wheels_path)

    return wheels


def _pip(venv=None):
    pip_module = 'pip'

    return [_get_python_path(venv), '-m', pip_module]


def _construct_pip_command(package,
                           wheels_path,
                           venv,
                           requirement_files=None,
                           upgrade=False,
                           install_args=None):
    requirement_files = requirement_files or []

    pip_command = _pip(venv) + ['install']
    for req_file in requirement_files:
        pip_command.extend(['-r', req_file])
    pip_command += [
        package, '--no-index', '--find-links', wheels_path, '--pre'
    ]
    if upgrade:
        pip_command.append('--upgrade')
    if install_args:
        if not isinstance(install_args, list):
            install_args = shlex.split(install_args, posix=not IS_WIN)
        pip_command += install_args
    return pip_command


def install_package(package,
                    wheels_path,
                    venv=None,
                    requirement_files=None,
                    upgrade=False,
                    install_args=None):
    """Install a Python package.

    Can specify a specific version.
    Can specify a prerelease.
    Can specify a venv to install in.
    Can specify a list of paths or urls to requirement txt files.
    Can specify a local wheels_path to use for offline installation.
    Can request an upgrade.
    """
    requirement_files = requirement_files or []

    logger.info('Installing %s...', package)
    if venv and not os.path.isdir(venv):
        raise WagonError('virtualenv {0} does not exist'.format(venv))

    pip_command = _construct_pip_command(
        package,
        wheels_path,
        venv,
        requirement_files,
        upgrade,
        install_args)

    if IS_VIRTUALENV and not venv:
        logger.info('Installing within current virtualenv')

    result = _run(pip_command)
    if not result.returncode == 0:
        raise WagonError(
            'Could not install package: {0} (`{1}` returned `{2}`)'.format(
                package, pip_command, result.aggr_stderr))


def _get_downloaded_wheels(path):
    return sorted([filename for filename in os.listdir(path)
                   if os.path.splitext(filename)[1].lower() == '.whl'])


def _open_url(url):
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

    return response


def _download_file(url, destination):
    logger.info('Downloading %s to %s...', url, destination)

    response = _open_url(url)

    if not response.code == 200:
        raise WagonError(
            "Failed to download file. Request to {0} "
            "failed with HTTP Error: {1}".format(url, response.code))
    final_url = response.geturl()
    if final_url != url and is_verbose():
        logger.debug('Redirected to %s', final_url)
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
    logger.info('Creating zip archive: %s...', destination)
    with closing(zipfile.ZipFile(destination, 'w')) as zip_file:
        for root, _, files in os.walk(source):
            for filename in files:
                file_path = os.path.join(root, filename)
                source_dir = os.path.dirname(source)
                zip_file.write(
                    file_path, os.path.relpath(file_path, source_dir))


def _unzip(archive, destination):
    logger.debug('Extracting zip %s to %s...', archive, destination)
    with closing(zipfile.ZipFile(archive, 'r')) as zip_file:
        zip_file.extractall(destination)


def _tar(source, destination):
    logger.info('Creating tgz archive: %s...', destination)
    with closing(tarfile.open(destination, 'w:gz')) as tar:
        tar.add(source, arcname=os.path.basename(source))


def _untar(archive, destination):
    logger.debug('Extracting tgz %s to %s...', archive, destination)
    with closing(tarfile.open(name=archive)) as tar:
        tar.extractall(path=destination, members=tar.getmembers())


def _get_wheel_tags(wheel_name):
    filename, _ = os.path.splitext(os.path.basename(wheel_name))
    return filename.split('-')


def _get_platform_from_wheel_name(wheel_name):
    """Extract the platform of a wheel from its file name.
    """
    return _get_wheel_tags(wheel_name)[-1]


def _get_platform_for_set_of_wheels(wheels_path):
    """For any set of wheel files, extracts a single platform.

    Since a set of wheels created or downloaded on one machine can only
    be for a single platform, if any wheel in the set has a platform
    which is not `any`, it will be used with one exception:

    In Linux, a wagon can contain wheels for both manylinux1 and linux.
    If, at any point we find that a wheel has `linux` as a platform,
    it will be used since it means it doesn't cross-fit all distros.

    If a platform other than `any` was not found, `any` will be assumed
    """
    real_platform = ''

    for wheel in _get_downloaded_wheels(wheels_path):
        platform = _get_platform_from_wheel_name(
            os.path.join(wheels_path, wheel))
        if 'linux' in platform and 'manylinux' not in platform:
            # Means either linux_x64_86 or linux_i686 on all wheels
            # If, at any point, a wheel matches this, it will be
            # returned so it'll only match that platform.
            return platform
        elif platform != ALL_PLATFORMS_TAG:
            # Means it can be either Windows, OSX or manylinux1 on all wheels
            real_platform = platform

    return real_platform or ALL_PLATFORMS_TAG


def _get_python_version():
    version = sys.version_info
    return 'py{0}{1}'.format(version[0], version[1])


def get_platform():
    return distutils.util.get_platform().replace('.', '_').replace('-', '_')


def _get_os_properties():
    """Retrieve distribution properties.

    **Note that platform.linux_distribution and platform.dist are deprecated
    and will be removed in Python 3.7. By that time, distro will become
    mandatory.
    """
    os_properties = {
        'distribution': None,
        'distribution_version': None,
        'distribution_release': None,
    }

    try:
        distribution, version, release = linux_distribution(
            full_distribution_name=False,
        )

        os_properties['distribution'] = distribution.lower()
        os_properties['distribution_version'] = version.lower()
        os_properties['distribution_release'] = release.lower()
    except TypeError:
        pass

    return os_properties


def _get_python_path(venv=None):
    if not venv:
        return sys.executable
    if IS_WIN:
        return os.path.join(venv, 'Scripts', 'python.exe')
    else:
        return os.path.join(venv, 'bin', 'python')


def _check_installed(package, venv=None):
    process = _run(_pip(venv) + ['freeze'])
    pkgs = ['{0}=='.format(package), '{0}=='.format(package.replace('_', '-'))]
    if any(package_name in process.aggr_stdout for package_name in pkgs):
        logger.debug('Package %s is installed in %s', package, venv)
        return True
    logger.debug('Package %s is not installed in %s', package, venv)
    return False


def _make_virtualenv(virtualenv_dir=None):
    if not virtualenv_dir:
        virtualenv_dir = tempfile.mkdtemp()
    logger.debug('Creating Virtualenv %s...', virtualenv_dir)
    venv.create(virtualenv_dir, with_pip=True)
    return virtualenv_dir


def _get_package_info_from_pypi(source):
    pypi_url = DEFAULT_INDEX_SOURCE_URL_TEMPLATE.format(source)
    if is_verbose():
        logger.debug('Getting metadata for %s from %s...', source, pypi_url)
    package_data = json.loads(_http_request(pypi_url))
    return package_data['info']


def _get_wagon_version():
    return pkg_resources.get_distribution('wagon').version


def _set_python_versions(python_versions=None):
    if python_versions:
        return ['py{0}'.format(version) for version in python_versions]
    else:
        return [_get_python_version()]


def _set_python_requires(wheels_path):
    python_requires = set()
    wheels = _get_downloaded_wheels(wheels_path)

    for _wheel in wheels:
        wheel_path = os.path.join(wheels_path, _wheel)
        package = Wheel(wheel_path)

        if package.requires_python:
            python_requires.add(package.requires_python)

    return ','.join(python_requires)


def _get_name_and_version_from_setup(source_path):

    def get_arg(arg_type, setuppy_path):
        return _run([
            sys.executable, setuppy_path, '--' + arg_type
        ]).aggr_stdout.strip()

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
                            python_requires,
                            package_name,
                            package_version,
                            build_tag,
                            package_source,
                            wheels,
                            files):
    """Generate a metadata file for the package.
    """
    logger.debug('Generating Metadata...')
    metadata = {
        'created_by_wagon_version': _get_wagon_version(),
        'archive_name': archive_name,
        'supported_platform': platform,
        'supported_python_versions': python_versions,
        'python_requires': python_requires,
        'build_server_os_properties': {
            'distribution': None,
            'distribution_version': None,
            'distribution_release': None,
        },
        'package_name': package_name,
        'package_version': package_version,
        'package_build_tag': build_tag,
        'package_source': package_source,
        'wheels': wheels,
        'files': files,
    }
    if IS_LINUX and platform != ALL_PLATFORMS_TAG:
        metadata.update(
            {
                'build_server_os_properties': _get_os_properties(),
            }
        )

    formatted_metadata = json.dumps(metadata, indent=4, sort_keys=True)
    if is_verbose():
        logger.debug('Metadata is: %s', formatted_metadata)
    output_path = os.path.join(workdir, METADATA_FILE_NAME)
    with open(output_path, 'w') as f:
        logger.debug('Writing metadata to file: %s', output_path)
        f.write(formatted_metadata)


def _set_archive_name(package_name,
                      package_version,
                      python_versions,
                      platform,
                      build_tag=''):
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
    ]

    if build_tag:
        archive_name_tags.insert(2, build_tag)

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


def _create_wagon_archive(source_path, archive_path, archive_format='tar.gz'):
    if archive_format.lower() == 'zip':
        _zip(source_path, archive_path)
    elif archive_format.lower() == 'tar.gz':
        _tar(source_path, archive_path)
    else:
        raise WagonError(
            'Unsupported archive format to create: {0} '
            '(Must be one of [zip, tar.gz]).'.format(archive_format.lower()))


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
        try:
            source = extract_source(source, tmpdir)
        except Exception:
            shutil.rmtree(tmpdir)
            raise
    elif os.path.isdir(os.path.expanduser(source)):
        source = os.path.expanduser(source)
    elif '==' in source:
        base_name, version = source.split('==')
        source = _get_package_info_from_pypi(base_name)['name']
        source = '{0}=={1}'.format(source, version)
    else:
        source = _get_package_info_from_pypi(source)['name']
    logger.debug('Source is: %s', source)
    return source


def _get_metadata(source_path):
    with open(os.path.join(source_path, METADATA_FILE_NAME)) as metadata_file:
        metadata = json.loads(metadata_file.read())
    return metadata


def create(source,
           requirement_files=None,
           force=False,
           keep_wheels=False,
           archive_destination_dir='.',
           python_versions=None,
           validate_archive=False,
           wheel_args='',
           archive_format='zip',
           build_tag='',
           pip_paths=None,
           supported_platform=None,
           add_file=None):
    """Create a Wagon archive and returns its path.

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
    _assert_linux_distribution_exists()

    logger.info('Creating archive for %s...', source)
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
    files_path = os.path.join(workdir, DEFAULT_FILES_PATH)
    files = []
    pip_paths = pip_paths if pip_paths else [None]
    try:
        for pip_path in pip_paths:
            wheels = wheel(
                processed_source,
                requirement_files,
                wheels_path,
                wheel_args,
                pip_path)
    finally:
        if processed_source != source:
            shutil.rmtree(processed_source, ignore_errors=True)

    platform = _get_platform_for_set_of_wheels(wheels_path)
    if supported_platform is not None:
        platform = supported_platform
    elif 'manylinux' in platform:
        # this is a hack to support Cloudify 5.1, who doesn't handle
        # manylinux wagons. Rename manylinux{1,2010,2014} to linux.
        # handle new wheel naming convention manylinux*.manylinux*
        # by getting the last part of platform
        # example :
        # >>> arch='manylinux_2_5_x86_64.manylinux1_x86_64'
        # >>> arch != 'x86_64' and arch.count('_')>0:
        # ...     arch = arch.partition('_')[2]
        # >>> arch
        # 'x86_64'
        # >>> arch="manylinux_2_5_x86_64"
        # >>> while arch != 'x86_64' and arch.count('_')>0:
        # ...     arch = arch.partition('_')[2]
        # >>> arch
        # 'x86_64'
        # >>> arch="manylinux_2_12_i686.manylinux2010_i686"
        # >>> while arch != 'x86_64' and arch.count('_')>0:
        # ...     arch = arch.partition('_')[2]
        # >>> arch
        # 'i686'
        arch = platform
        while arch != 'x86_64' and arch.count('_') > 0:
            arch = arch.partition('_')[2]
        platform = 'linux_{0}'.format(arch or 'x86_64')

    if is_verbose():
        logger.debug('Platform is: %s', platform)

    python_versions = _set_python_versions(python_versions)
    python_requires = _set_python_requires(wheels_path)

    if not os.path.isdir(archive_destination_dir):
        os.makedirs(archive_destination_dir)
    archive_name = _set_archive_name(
        package_name, package_version, python_versions, platform, build_tag)
    archive_path = os.path.join(archive_destination_dir, archive_name)

    _handle_output_file(archive_path, force)

    if add_file:
        for source_path in add_file:
            if _validate_file_path(source_path):
                os.makedirs(
                    files_path,
                    exist_ok=True,
                )
                filename = os.path.basename(source_path)
                destination_path = os.path.join(
                    files_path,
                    filename,
                )
                shutil.copy(
                    source_path,
                    destination_path,
                )
                files.append(
                    os.path.basename(
                        destination_path,
                    )
                )

    _generate_metadata_file(
        workdir,
        archive_name,
        platform,
        python_versions,
        python_requires,
        package_name,
        package_version,
        build_tag,
        source,
        wheels,
        files,
    )

    _create_wagon_archive(workdir, archive_path, archive_format)
    if not keep_wheels:
        logger.debug('Removing work directory...')
        shutil.rmtree(tempdir, ignore_errors=True)

    if validate_archive:
        validate(archive_path)
    logger.info('Wagon created successfully at: %s', archive_path)
    return archive_path


def _is_platform_supported(supported_platform, machine_platform):
    if not IS_LINUX and machine_platform != supported_platform:
        return False
    elif IS_LINUX:
        if 'manylinux' not in supported_platform \
                and machine_platform != supported_platform:
            return False

        machine_arch = machine_platform.split('_')[1]
        supported_arch = supported_platform.split('_')[1]
        if supported_arch != machine_arch:
            return False
    return True


def install(source,
            venv=None,
            requirement_files=None,
            upgrade=False,
            ignore_platform=False,
            install_args=''):
    """Install a Wagon archive.

    This can install in a provided `venv` or in the current
    virtualenv in case one is currently active.

    `upgrade` is merely pip's upgrade.

    `ignore_platform` will allow to ignore the platform check, meaning
    that if an archive was created for a specific platform (e.g. win32),
    and the current platform is different, it will still attempt to
    install it.

    Platform check will fail on the following:

    If not linux and no platform match (e.g. win32 vs. darwin)
    If linux and:
        architecture doesn't match (e.g. manylinux1_x86_64 vs. linux_i686)
        wheel not manylinux and no platform match (linux_x86_64 vs. linux_i686)
    """
    requirement_files = requirement_files or []

    logger.info('Installing %s', source)
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)

    def raise_unsupported_platform(machine_platform):
        # TODO: Print which platform is supported?
        raise WagonError(
            'Platform unsupported for wagon ({0})'.format(
                machine_platform))

    try:
        supported_platform = metadata['supported_platform']
        if not ignore_platform and supported_platform != ALL_PLATFORMS_TAG:
            logger.debug(
                'Validating Platform %s is supported...', supported_platform)
            machine_platform = get_platform()
            if not _is_platform_supported(
                    supported_platform, machine_platform):
                raise_unsupported_platform(machine_platform)

        wheels_path = os.path.join(processed_source, DEFAULT_WHEELS_PATH)
        install_package(
            metadata['package_name'],
            wheels_path,
            venv,
            requirement_files,
            upgrade,
            install_args)
    finally:
        # Install can only be done on local or remote archives.
        # This means that a temporary directory is always created
        # with the sources to install within it. This is why we can allow
        # ourselves to delete the parent dir without worrying.
        # TODO: Make this even less dangerous by changing `get_source`
        # to return the directory to delete instead. Much safer.
        if processed_source != source:
            shutil.rmtree(os.path.dirname(
                processed_source), ignore_errors=True)


def validate(source):
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

    logger.info('Validating %s', source)
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
        install(source=processed_source, venv=tmpenv)
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
        logger.info('Source can be found at: %s', processed_source)
    else:
        logger.info('Validation Passed!')
        if processed_source != source:
            shutil.rmtree(processed_source)
    return validation_errors


def show(source):
    """Merely returns the metadata for the provided archive.
    """
    if is_verbose():
        logger.info('Retrieving Metadata for: %s', source)
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)
    shutil.rmtree(processed_source)
    return metadata


def list_files(source):
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)

    shutil.rmtree(
        processed_source,
        ignore_errors=True,
    )

    return metadata['files']


def get_file(source, filename, output_directory='.'):
    processed_source = get_source(source)

    source_path = os.path.join(processed_source, 'files', filename)
    destination_path = os.path.join(output_directory, filename)
    absolute_destination_path = os.path.abspath(destination_path)

    if os.path.isfile(source_path):
        shutil.copy(
            source_path,
            destination_path,
        )
    else:
        absolute_destination_path = None

    shutil.rmtree(
        processed_source,
        ignore_errors=True,
    )

    return absolute_destination_path


def _repair_wheels(workdir, metadata):
    wheels_path = os.path.join(workdir, DEFAULT_WHEELS_PATH)

    for wheel in _get_downloaded_wheels(wheels_path):
        if _get_platform_from_wheel_name(wheel).startswith('linux'):
            wheel_path = os.path.join(wheels_path, wheel)
            outcome = _run(
                ['auditwheel', 'repair', wheel_path, '-w', wheels_path])
            if outcome.returncode != 0:
                raise WagonError('Failed to repair wagon')
            os.remove(wheel_path)

    # Note that at this point, _get_downloaded_wheels will return
    # a different set of wheels which have been repaired.
    updated_wheels = _get_downloaded_wheels(wheels_path)
    for wheel in updated_wheels:
        manylinux1_platform = _get_platform_from_wheel_name(wheel)
        if manylinux1_platform.startswith('manylinux1'):
            # It's enough to get the new platform from a single
            # repaired wheel.
            break

    # TODO: Return this and update in another function
    metadata['wheels'] = updated_wheels
    metadata['supported_platform'] = manylinux1_platform

    metadata.update(
        {
            'build_server_os_properties': _get_os_properties(),
        }
    )
    return metadata


def _assert_linux_distribution_exists():
    if linux_distribution is None:
        raise WagonError(
            'Could not determine platform information. To build or '
            'repair wagons on python 3.8+, install distro (eg. by '
            'installing wagon[dist].')


def _assert_auditwheel_exists():
    if not find_executable('auditwheel'):
        raise WagonError(
            'Could not find auditwheel. '
            'Please make sure auditwheel is installed and is in the PATH.\n'
            'Please see https://github.com/pypa/auditwheel for more info.')


def repair(source, validate_archive=False):
    """Use auditwheel (https://github.com/pypa/auditwheel)
    to attempt and repair all wheels in a wagon.

    The repair process will:

    1. Extract the wagon and its metadata
    2. Repair all wheels
    3. Update the metadata with the new wheel names and platform
    4. Repack the wagon
    """
    _assert_auditwheel_exists()

    logger.info('Repairing: %s', source)
    processed_source = get_source(source)
    metadata = _get_metadata(processed_source)
    new_metadata = _repair_wheels(processed_source, metadata)

    archive_name = _set_archive_name(
        new_metadata['package_name'],
        new_metadata['package_version'],
        new_metadata['supported_python_versions'],
        new_metadata['supported_platform'],
        new_metadata['build_tag'])

    _generate_metadata_file(
        processed_source,
        archive_name,
        new_metadata['supported_platform'],
        new_metadata['supported_python_versions'],
        new_metadata['python_requires'],
        new_metadata['package_name'],
        new_metadata['package_version'],
        new_metadata['build_tag'],
        new_metadata['package_source'],
        new_metadata['wheels'])
    archive_path = os.path.join(os.getcwd(), archive_name)
    _create_wagon_archive(processed_source, archive_path)

    if validate_archive:
        validate(archive_path)
    logger.info('Wagon created successfully at: %s', archive_path)
    return archive_path


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
            archive_format=args.format,
            build_tag=args.build_tag,
            pip_paths=args.pip or [None],
            supported_platform=args.supported_platform,
            add_file=args.add_file,
        )
    except WagonError as ex:
        sys.exit(ex)


def _install_wagon(args):
    try:
        install(
            source=args.SOURCE,
            requirement_files=args.requirements_file,
            upgrade=args.upgrade,
            ignore_platform=args.ignore_platform,
            install_args=args.install_args)
    except WagonError as ex:
        sys.exit(ex)


def _list_files(args):
    try:
        files = list_files(
            source=args.SOURCE,
        )

        if len(files) > 0:
            logger.info('List of files:')
            for file in files:
                logger.info(f'  {file}')
        else:
            logger.info('There are no files.')
    except WagonError as ex:
        sys.exit(ex)


def _get_file(args):
    try:
        file_path = get_file(
            source=args.SOURCE,
            filename=args.filename,
            output_directory=args.output_directory,
        )

        if file_path:
            logger.info(f'File was saved in: {file_path}')
        else:
            logger.info('File does not exist!')
    except WagonError as ex:
        sys.exit(ex)


def _validate_wagon(args):
    try:
        if len(validate(args.SOURCE)) > 0:
            sys.exit(1)
    except WagonError as ex:
        sys.exit(ex)


def _show_wagon(args):
    # We set this to reduce logging so that only the metadata is shown
    # without additional logging.
    logger.setLevel(logging.DEBUG if is_verbose() else logging.INFO)
    try:
        metadata = show(args.SOURCE)
        print(json.dumps(metadata, indent=4, sort_keys=True))
    except WagonError as ex:
        sys.exit(ex)


def _repair_wagon(args):
    try:
        repair(args.SOURCE, args.validate)
    except WagonError as ex:
        sys.exit(ex)


def _add_verbose_argument(parser):
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Set verbose logging level')
    return parser


def _set_defaults(parser, func):
    parser = _add_verbose_argument(parser)
    parser.set_defaults(func=func)
    return parser


def _add_create_command(parser):
    description = ('Create a Wagon archive')

    command = parser.add_parser(
        'create',
        description=description,
        help=description)

    source_help = (
        'The source from which to create the archive. '
        'Possible formats are:'
        'PACKAGE_NAME, PACKAGE_NAME==PACKAGE_VERSION, '
        'https://github.com/org/repo/archive/branch.extension, '
        '/path/to/github/like/archive, '
        '/path/to/package/where/setup.py/resides'
    )
    command.add_argument('SOURCE', help=source_help)

    command.add_argument(
        '-r',
        '--requirements-file',
        action='append',
        help='Whether to also pack wheels from a requirements file. '
             'This argument can be provided multiple times')
    command.add_argument(
        '-t',
        '--format',
        required=False,
        default='zip',
        choices=(['zip', 'tar.gz']),
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
        '--build-tag',
        default='',
        help='A build number for the archive')
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

    command.add_argument(
        '--pip',
        default=None,
        required=False,
        action='append',
        help='Path to pip, used for packaging and downloading wheels '
             '(eg. one py2, one py3) .'
             'This argument can be provided multiple times.')

    command.add_argument(
        '--supported-platform',
        default=None,
        required=False,
        help='Platform supported by the wagon (eg. linux_x86_64 '
             'or manylinux1).')

    command.add_argument(
        '--add-file',
        type=str,
        nargs='+',
        default=None,
        required=False,
        help='Path to add to the Wagon.'
    )

    _set_defaults(command, func=_create_wagon)
    return parser


def _add_wagon_archive_source_argument(parser):
    source_help = (
        'The source from which to create the archive. '
        'Possible formats are:'
        'URL to wagon archive, '
        '/path/to/wagon/archive'
    )
    parser.add_argument('SOURCE', help=source_help)
    return parser


def _add_install_command(parser):
    description = ('Install a Wagon archive')

    command = parser.add_parser(
        'install',
        description=description,
        help=description)

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

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_install_wagon)
    return parser


def _add_validate_command(parser):
    description = (
        "Validate an archive\n\nThis validates that the archive's "
        "structure is one of a valid wagon and\nthat all required "
        "wheels exist, after which it creates a virtualenv and\n"
        "installs the package into it."
    )

    command = parser.add_parser(
        'validate',
        description=description,
        help='Validate a wagon archive')

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_validate_wagon)
    return parser


def _add_show_command(parser):
    description = ('Print out the metadata of a wagon')

    command = parser.add_parser(
        'show',
        description=description,
        help=description)

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_show_wagon)
    return parser


def _add_repair_command(parser):
    description = (
        'Use auditwheel to repair all wheels in a wagon. \n\n'
        'Note that this requires a specific environment where\n'
        'auditwheel can work and you must install auditwheel\n'
        'manually. For more information, '
        'see https://github.com/pypa/auditwheel.'
    )

    command = parser.add_parser(
        'repair',
        description=description,
        help='Repair a Wagon archive')

    command.add_argument(
        '--validate',
        default=False,
        action='store_true',
        help='Runs a postcreation validation on the archive')

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_repair_wagon)
    return parser


def _add_list_files_command(parser):
    description = ('List Wagon archive files')

    command = parser.add_parser(
        'list-files',
        description=description,
        help=description,
    )

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_list_files)

    return parser


def _add_get_file_command(parser):
    description = ('Get file from Wagon archive')

    command = parser.add_parser(
        'get-file',
        description=description,
        help=description,
    )

    command.add_argument(
        '-f',
        '--filename',
        required=True,
        help='Filename to get from Wagon',
    )

    command.add_argument(
        '-o',
        '--output-directory',
        default='.',
        help='Output directory for the file',
    )

    _add_wagon_archive_source_argument(command)
    _set_defaults(command, func=_get_file)

    return parser


def _validate_file_path(path):
    return os.path.isfile(path)


# TODO: Find a way to both provide an error handler AND multiple formatter
# classes.
class CustomFormatter(argparse.ArgumentParser):
    def error(self, message):
        # We want to make sure that when there are missing or illegal arguments
        # we error out informatively.
        self.print_help()
        sys.exit('\nerror: %s\n' % message)


def _assert_atleast_one_arg(parser):
    """When simply running `wagon`, this will make sure we exit without
    erroring out.
    """
    if len(sys.argv) == 1:
        parser.print_help()
        parser.exit(0)


def parse_args():
    parser = CustomFormatter(
        description=DESCRIPTION,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser = _add_verbose_argument(parser)

    subparsers = parser.add_subparsers()
    subparsers = _add_create_command(subparsers)
    subparsers = _add_install_command(subparsers)
    subparsers = _add_validate_command(subparsers)
    subparsers = _add_show_command(subparsers)
    subparsers = _add_repair_command(subparsers)
    subparsers = _add_list_files_command(subparsers)
    subparsers = _add_get_file_command(subparsers)

    _assert_atleast_one_arg(parser)

    return parser.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        set_verbose()
    args.func(args)


if __name__ == '__main__':
    main()
