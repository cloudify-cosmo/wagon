import os
import subprocess
import re
import urllib
import tarfile
import logging
from threading import Thread
import time
import sys
from contextlib import closing
import platform

import codes
import logger


IS_VIRTUALENV = hasattr(sys, 'real_prefix')

PLATFORM = sys.platform
IS_WIN = (PLATFORM == 'win32')
IS_DARWIN = (PLATFORM == 'darwin')
IS_LINUX = (PLATFORM == 'linux2')

PROCESS_POLLING_INTERVAL = 0.1

lgr = logger.init()


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


# TODO: implement using sh
def run(cmd, suppress_errors=False, suppress_output=False):
    """Executes a command
    """
    lgr.debug('Executing: {0}...'.format(cmd))
    pipe = subprocess.PIPE
    proc = subprocess.Popen(cmd, shell=True, stdout=pipe, stderr=pipe)

    stderr_log_level = logging.NOTSET if suppress_errors else logging.ERROR
    stdout_log_level = logging.NOTSET if suppress_errors else logging.DEBUG

    stdout_thread = PipeReader(proc.stdout, proc, lgr, stdout_log_level)
    stderr_thread = PipeReader(proc.stderr, proc, lgr, stderr_log_level)

    stdout_thread.start()
    stderr_thread.start()

    while proc.poll() is None:
        time.sleep(PROCESS_POLLING_INTERVAL)

    stdout_thread.join()
    stderr_thread.join()

    proc.aggr_stdout = stdout_thread.aggr
    proc.aggr_stderr = stderr_thread.aggr

    return proc


def wheel(module, requirement_files=False, wheels_dir='module'):
    lgr.info('Downloading Wheels for {0}...'.format(module))
    wheel_cmd = ['pip', 'wheel']
    wheel_cmd.append('--wheel-dir={0}'.format(wheels_dir))
    wheel_cmd.append('--find-links={0}'.format(wheels_dir))
    if requirement_files:
        for req_file in requirement_files:
            wheel_cmd.extend(['-r', req_file])
    wheel_cmd.append(module)
    p = run(' '.join(wheel_cmd))
    if not p.returncode == 0:
        lgr.error('Could not download wheels for: {0}. '
                  'Please verify that the module you are trying '
                  'to wheel is wheelable.'.format(module))
        sys.exit(codes.errors['failed_to_wheel'])


def install_module(module, wheels_path, virtualenv_path=None,
                   requirements_file=None, upgrade=False):
    """This will install a Python module.

    Can specify a specific version.
    Can specify a prerelease.
    Can specify a virtualenv to install in.
    Can specify a list of paths or urls to requirement txt files.
    Can specify a local wheels_path to use for offline installation.
    Can request an upgrade.
    """
    lgr.info('Installing {0}...'.format(module))

    pip_cmd = ['pip', 'install']
    if virtualenv_path:
        pip_cmd[0] = os.path.join(
            _get_env_bin_path(virtualenv_path), pip_cmd[0])
    if requirements_file:
        pip_cmd.extend(['-r', requirements_file])
    pip_cmd.append(module)
    pip_cmd.extend(['--use-wheel', '--no-index', '--find-links', wheels_path])
    # pre allows installing both prereleases and regular releases depending
    # on the wheels provided.
    pip_cmd.append('--pre')
    if upgrade:
        pip_cmd.append('--upgrade')
    if IS_VIRTUALENV and not virtualenv_path:
        lgr.info('Installing within current virtualenv: {0}...'.format(
            IS_VIRTUALENV))
    result = run(' '.join(pip_cmd))
    if not result.returncode == 0:
        lgr.error(result.aggr_stdout)
        lgr.error('Could not install module: {0}.'.format(module))
        sys.exit(codes.errors['failed_to_install_module'])


def get_downloaded_wheels(wheels_path):
    """Returns a list of a set of wheel files.
    """
    return [f for f in os.listdir(wheels_path) if f.endswith('whl')]


def download_file(url, destination):
    lgr.info('Downloading {0} to {1}...'.format(url, destination))
    final_url = urllib.urlopen(url).geturl()
    if final_url != url:
        lgr.debug('Redirected to {0}'.format(final_url))
    f = urllib.URLopener()
    f.retrieve(final_url, destination)


def tar(source, destination):
    lgr.info('Creating tar file: {0}...'.format(destination))
    with closing(tarfile.open(destination, "w:gz")) as tar:
        tar.add(source, arcname=os.path.basename(source))


def untar(archive, destination):
    """Extracts files from an archive to a destination folder.
    """
    lgr.debug('Extracting {0} to {1}...'.format(archive, destination))
    with closing(tarfile.open(name=archive)) as tar:
        files = [f for f in tar.getmembers()]
        tar.extractall(path=destination, members=files)


def get_platform_from_wheel_name(wheel_name):
    """Extracts the platform of a wheel from its file name.
    """
    lgr.debug('Getting platform for wheel: {0}...'.format(wheel_name))
    filename, _ = os.path.splitext(os.path.basename(wheel_name))
    name_parts = filename.split('-')
    return name_parts[-1]


def get_platform_for_set_of_wheels(wheels_dir):
    """For any set of wheel files, extracts a single platform.

    Since a set of wheels created or downloaded on one machine can only
    be for a single platform, if any wheel in the set has a platform
    which is not `any`, it will be used. If a platform other than
    `any` was not found, `any` will be assumed.
    """
    lgr.debug('Setting platform for wheels in: {0}...'.format(wheels_dir))
    for wheel in get_downloaded_wheels(wheels_dir):
        platform = get_platform_from_wheel_name(
            os.path.join(wheels_dir, wheel))
        if platform != 'any':
            return platform
    return 'any'


def get_python_version():
    version = sys.version_info
    return 'py{0}{1}'.format(version[0], version[1])


def get_machine_platform():
    id = '{0}_{1}'.format(platform.system().lower(), platform.machine())
    lgr.info('Identified machine platform: {0}'.format(id))
    return id


def get_os_properties():
    return platform.linux_distribution(full_distribution_name=False)


def _get_env_bin_path(env_path):
    """Returns the bin path for a virtualenv
    """
    try:
        import virtualenv
        return virtualenv.path_locations(env_path)[3]
    except ImportError:
        # this is a fallback for a race condition in which you're trying
        # to use the script and create a virtualenv from within
        # a virtualenv in which virtualenv isn't installed and so
        # is not importable.
        return os.path.join(env_path, 'scripts' if IS_WIN else 'bin')


def check_installed(module, virtualenv):
    """Checks to see if a module is installed within a virtualenv.
    """
    pip_path = os.path.join(_get_env_bin_path(virtualenv), 'pip')
    p = run('{0} freeze'.format(pip_path), suppress_output=True)
    if re.search(r'{0}'.format(module), p.aggr_stdout.lower()):
        lgr.debug('Module {0} is installed in {1}'.format(module, virtualenv))
        return True
    lgr.debug('Module {0} is not installed in {1}'.format(module, virtualenv))
    return False


def make_virtualenv(virtualenv_dir, python_path='python'):
    """This will create a virtualenv.
    """
    lgr.info('Creating Virtualenv {0}...'.format(virtualenv_dir))
    result = run('virtualenv -p {0} {1}'.format(python_path, virtualenv_dir))
    if not result.returncode == 0:
        lgr.error('Could not create virtualenv: {0}'.format(virtualenv_dir))
        sys.exit(codes.errors['failed_to_create_virtualenv'])
