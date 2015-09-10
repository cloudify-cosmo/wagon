import os
import subprocess
import logger
import urllib
import tarfile
import logging
from threading import Thread
import time
import sys
from contextlib import closing

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
                self.logger.log(self.log_level, output)
            else:
                time.sleep(PROCESS_POLLING_INTERVAL)


# TODO: implement using sh
def run(cmd, suppress_errors=False):
    """Executes a command
    """
    lgr.debug('Executing: {0}...'.format(cmd))
    pipe = subprocess.PIPE
    proc = subprocess.Popen(cmd, shell=True, stdout=pipe, stderr=pipe)

    stderr_log_level = logging.NOTSET if suppress_errors else logging.ERROR

    stdout_thread = PipeReader(proc.stdout, proc, lgr, logging.DEBUG)
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


def wheel(module, pre=False, requirement_files=False, wheels_dir='plugin'):
    lgr.info('Downloading Wheels for {0}...'.format(module))
    wheel_cmd = ['pip', 'wheel']
    wheel_cmd.append('--wheel-dir={0}'.format(wheels_dir))
    wheel_cmd.append('--find-links={0}'.format(wheels_dir))
    if pre:
        wheel_cmd.append('--pre')
    if requirement_files:
        for req_file in requirement_files:
            wheel_cmd.extend(['-r', req_file])
    wheel_cmd.append(module)
    p = run(' '.join(wheel_cmd))
    if not p.returncode == 0:
        lgr.error('Could not download wheels for: {0}. '
                  'Please verify that the module you are trying '
                  'to wheel is wheelable.'.format(module))
        sys.exit(1)


def get_downloaded_wheels(wheels_path):
    """Returns a list of a set of wheel files.
    """
    return [f for f in os.listdir(wheels_path) if f.endswith('whl')]


def download_file(url, destination):
    lgr.info('Downloading {0} to {1}'.format(url, destination))
    final_url = urllib.urlopen(url).geturl()
    if final_url != url:
        lgr.debug('Redirected to {0}'.format(final_url))
    f = urllib.URLopener()
    f.retrieve(final_url, destination)


def tar(source, destination):
    lgr.info('Creating tar file: {0}'.format(destination))
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
    lgr.debug('Getting platform from wheel: {0}'.format(wheel_name))
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
    lgr.debug('Getting platform wheels in: {0}.'.format(wheels_dir))
    for wheel in get_downloaded_wheels(wheels_dir):
        platform = get_platform_from_wheel_name(
            os.path.join(wheels_dir, wheel))
        if platform != 'any':
            return platform
    return 'any'


def get_python_version():
    version = sys.version_info
    return 'py{0}{1}'.format(version[0], version[1])
