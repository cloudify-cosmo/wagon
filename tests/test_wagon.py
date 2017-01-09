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
import sys
import json
import shutil
import tarfile
import tempfile
import subprocess
from contextlib import closing

import mock
import pytest
import virtualenv  # NOQA

import wagon

IS_PY3 = wagon.IS_PY3

TEST_TAR = 'https://github.com/pallets/flask/archive/0.10.1.tar.gz'  # NOQA
TEST_ZIP = 'https://github.com/pallets/flask/archive/0.10.1.zip'  # NOQA
TEST_PACKAGE_NAME = 'Flask'
TEST_PACKAGE_VERSION = '0.10.1'
TEST_PACKAGE_PLATFORM = 'linux_x86_64'
TEST_PACKAGE = '{0}=={1}'.format(TEST_PACKAGE_NAME, TEST_PACKAGE_VERSION)


def _invoke(command):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True)
    stdout, stderr = process.communicate()
    process.stdout, process.stderr = \
        stdout.decode('ascii'), stderr.decode('ascii')
    return process


def _parse(command):
    sys.argv = command.split()
    wagon.main()


class TestBase:

    def test_run(self):
        proc = wagon._run('uname')
        assert proc.returncode == 0

    def test_run_bad_command(self):
        proc = wagon._run('suname')
        proc.returncode == (1 if wagon.IS_WIN else 127)

    def test_download_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        wagon._download_file(TEST_TAR, path)
        try:
            os.remove(path)
        except:
            pytest.xfail(
                "Failed to remove file, which means it was not downloaded")

    def test_download_file_missing(self):
        with pytest.raises(wagon.WagonError) as ex:
            wagon._download_file('http://www.google.com/x.tar.gz', 'file')
        assert "Failed to download file" in str(ex)

    def test_download_bad_url(self):
        if IS_PY3:
            with pytest.raises(ValueError) as ex:
                wagon._download_file('something', 'file')
            assert "unknown url type: 'something'" in str(ex.value)
        else:
            with pytest.raises(IOError) as ex:
                wagon._download_file('something', 'file')
            if wagon.IS_WIN:
                assert "cannot find the file specified: 'something'" \
                    in str(ex.value)
            else:
                assert "No such file or directory: 'something'" \
                    in str(ex.value)

    def test_download_missing_path(self):
        with pytest.raises(IOError) as ex:
            wagon._download_file(TEST_TAR, 'x/file')
        assert 'No such file or directory' in str(ex.value)

    @pytest.mark.skipif(wagon.IS_WIN, reason='Irrelevant on Windows')
    def test_download_no_permissions(self):
        with pytest.raises(IOError) as ex:
            wagon._download_file(TEST_TAR, '/file')
        assert 'Permission denied' in str(ex)

    def test_tar(self):
        tempdir = tempfile.mkdtemp()
        with open(os.path.join(tempdir, 'content.file'), 'w') as f:
            f.write('CONTENT')
        wagon._tar(tempdir, 'tar.file')
        shutil.rmtree(tempdir)
        assert tarfile.is_tarfile('tar.file')
        with closing(tarfile.open('tar.file', 'r:gz')) as tar:
            members = tar.getnames()
            dirname = os.path.split(tempdir)[1]
            assert '{0}/content.file'.format(dirname) in members
        os.remove('tar.file')

    @pytest.mark.skipif(wagon.IS_WIN, reason='Irrelevant on Windows')
    def test_tar_no_permissions(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with pytest.raises(IOError) as ex:
                wagon._tar(tmpdir, '/file')
            assert "Permission denied" in str(ex.value)
            assert "/file" in str(ex.value)
        finally:
            shutil.rmtree(tmpdir)

    def test_tar_missing_source(self):
        with pytest.raises(OSError) as ex:
            wagon._tar('missing', 'file')
        if wagon.IS_WIN:
            assert "The system cannot find the file specified: 'missing'" \
                in str(ex.value)
        else:
            assert "No such file or directory" in str(ex.value)
            assert "missing" in str(ex.value)
        os.remove('file')

    def test_make_virtualenv(self):
        virtualenv_path = wagon._make_virtualenv()
        try:
            pip_path = wagon._get_pip_path(virtualenv_path)
            assert os.path.isfile(pip_path)
        finally:
            shutil.rmtree(virtualenv_path)

    def test_wheel_nonexisting_package(self):
        try:
            with pytest.raises(wagon.WagonError) as ex:
                wagon.wheel('cloudify-script-plug==1.3')
            assert 'Could not download wheels for:' in str(ex)
        finally:
            shutil.rmtree('package')

    @pytest.mark.skipif(not wagon.IS_WIN and not wagon.IS_LINUX,
                        reason='Not testing on all platforms')
    def test_machine_platform(self):
        assert ('win32' if wagon.IS_WIN else 'linux_x86_64') \
            in wagon.get_platform()

    def test_get_version_from_pypi_bad_source(self):
        with pytest.raises(wagon.WagonError) as ex:
            wagon._get_package_info_from_pypi('NONEXISTING_PACKAGE')
        assert 'Failed to retrieve info for package' in str(ex)

    def test_check_package_not_installed(self):
        virtualenv_path = wagon._make_virtualenv()
        try:
            result = wagon._check_installed(TEST_PACKAGE_NAME, virtualenv_path)
            assert not result
        finally:
            shutil.rmtree(virtualenv_path)

    def test_install_package_failed(self):
        with pytest.raises(wagon.WagonError) as ex:
            wagon.install_package('x', 'y')
        assert 'Could not install package:' in str(ex)

    def test_archive_unsupported_format(self):
        with pytest.raises(wagon.WagonError) as ex:
            wagon._create_wagon_archive(
                'source_dir',
                'output_archive',
                'unsupported_format')
        assert 'Unsupported archive format to create' in str(ex)

    def test_single_python_version(self):
        versions = wagon._set_python_versions()
        verinfo = sys.version_info
        version = ['py{0}{1}'.format(verinfo[0], verinfo[1])]
        assert versions == version

    def test_provided_python_version(self):
        provided_version_numbers = ['27', '26']
        versions = wagon._set_python_versions(provided_version_numbers)
        expected_versions = ['py27', 'py26']
        assert versions == expected_versions

    @pytest.mark.skipif(wagon.IS_WIN, reason='Irrelevant on Windows')
    @mock.patch('sys.executable', new='/a/b/c/python')
    def test_pip_path_on_not_windows(self):
        assert wagon._get_pip_path(venv='') == '/a/b/c/pip'

    @pytest.mark.skipif(not wagon.IS_WIN, reason='Irrelevant on non-Windows')
    @mock.patch('sys.executable', new='C:\Python27\python.exe')
    def test_pip_path_on_windows(self):
        assert wagon._get_pip_path(venv='') == 'C:\Python27\scripts\pip.exe'

    def test_get_downloaded_wheels(self):
        tempdir = tempfile.mkdtemp()
        fd, temp_wheel = tempfile.mkstemp(suffix='.whl', dir=tempdir)
        os.close(fd)
        fd, temp_non_wheel = tempfile.mkstemp(suffix='.zip', dir=tempdir)
        os.close(fd)
        temp_wheel_filename = os.path.basename(temp_wheel)
        temp_non_wheel_filename = os.path.basename(temp_non_wheel)
        try:
            wheels = wagon._get_downloaded_wheels(tempdir)
            assert temp_wheel_filename in wheels
            assert temp_non_wheel_filename not in wheels
        finally:
            shutil.rmtree(tempdir)

    def test_cli_too_few_arguments(self):
        with pytest.raises(SystemExit) as ex:
            _parse('wagon create')

        if wagon.IS_PY3:
            assert 'the following arguments are required' in str(ex.value)
        else:
            assert 'too few arguments' in str(ex.value)

    def test_cli_bad_argument(self):
        with pytest.raises(SystemExit) as ex:
            _parse('wagon create flask --non-existing-argument')
        assert 'error: unrecognized arguments: --non-existing-argument' \
            in str(ex.value)


class TestGetSource:
    def test_source_file_not_a_valid_archive(self):
        fd, source_input = tempfile.mkstemp()
        os.close(fd)
        # In python2.6, an empty file can be opened as a tar archive.
        # We fill it up so that it fails.
        with open(source_input, 'w') as f:
            f.write('something')

        try:
            with pytest.raises(wagon.WagonError) as ex:
                wagon.get_source(source_input)
            assert 'Failed to extract' in str(ex)
        finally:
            os.remove(source_input)

    def test_source_directory_not_a_package(self):
        source_input = tempfile.mkdtemp()

        try:
            with pytest.raises(wagon.WagonError) as ex:
                wagon.create(source_input)
            assert 'Source directory must contain a setup.py file' in str(ex)
        finally:
            shutil.rmtree(source_input)

    def test_source_pypi_no_version(self):
        source_input = TEST_PACKAGE_NAME
        source_output = wagon.get_source(source_input)
        assert source_output == \
            wagon._get_package_info_from_pypi(TEST_PACKAGE_NAME)['name']

    def test_source_pypi_with_version(self):
        source_input = TEST_PACKAGE
        source_output = wagon.get_source(source_input)
        test_package = '{0}=={1}'.format(
            wagon._get_package_info_from_pypi(TEST_PACKAGE_NAME)['name'],
            TEST_PACKAGE_VERSION)
        assert source_output == test_package


class TestCreateBadSources:
    def test_unsupported_url_schema(self):
        with pytest.raises(wagon.WagonError) as ex:
            wagon.create(source='ftp://x')
        assert 'Source URL type' in str(ex)


class TestCreate:

    def setup_method(self, test_method):
        if wagon.IS_WIN:
            self.platform = 'win32'
        else:
            self.platform = 'linux_x86_64'
        self.python_versions = [wagon._get_python_version()]
        self.package_version = TEST_PACKAGE_VERSION
        self.package_name = TEST_PACKAGE_NAME
        self.archive_name = wagon._set_archive_name(
            self.package_name,
            self.package_version,
            self.python_versions,
            self.platform)
        self.wagon_version = wagon._get_wagon_version()

    def teardown_method(self, test_method):
        if os.path.isfile(self.archive_name):
            os.remove(self.archive_name)
        if os.path.isdir(self.package_name):
            shutil.rmtree(self.package_name)

    def _test(self, result, expected_number_of_wheels=5):
        assert result.returncode == 0
        assert os.path.isfile(self.archive_name)

        try:
            wagon._untar(self.archive_name, '.')
        except:
            wagon._unzip(self.archive_name, '.')
        with open(os.path.join(
                self.package_name,
                wagon.METADATA_FILE_NAME)) as f:
            metadata = json.loads(f.read())

        assert self.wagon_version == metadata['created_by_wagon_version']
        assert self.package_version == metadata['package_version']
        assert self.package_name == metadata['package_name']
        assert self.platform == metadata['supported_platform']
        assert len(metadata['wheels']) == expected_number_of_wheels

        if wagon.IS_LINUX and self.platform != 'any':
            distro, version, release = wagon._get_os_properties()
            assert distro.lower() == \
                metadata['build_server_os_properties']['distribution']
            assert version.lower() == \
                metadata['build_server_os_properties']['distribution_version']
            assert release.lower() == \
                metadata['build_server_os_properties']['distribution_release']

        assert (
            '{0}-{1}-{2}-none-{3}'.format(
                self.package_name.replace('-', '_'),
                self.package_version,
                '.'.join(self.python_versions),
                self.platform) in metadata['archive_name'])

        return metadata

    def test_create_archive_from_pypi_with_version(self):
        result = _invoke('wagon create {0} -v -f '.format(TEST_PACKAGE))
        metadata = self._test(result)
        assert metadata['package_source'] == TEST_PACKAGE

    def test_create_zip_formatted_wagon_from_zip(self):
        self.archive_name = wagon._set_archive_name(
            TEST_PACKAGE_NAME,
            TEST_PACKAGE_VERSION,
            self.python_versions,
            self.platform)
        result = _invoke('wagon create {0} -v -f -t zip'.format(TEST_ZIP))
        metadata = self._test(result)
        assert metadata['package_source'] == TEST_ZIP

    def test_create_archive_from_pypi_with_additional_wheel_args(self):
        fd, reqs_file_path = tempfile.mkstemp()
        os.write(fd, b'virtualenv==13.1.2')
        result = _invoke(
            'wagon create {0} -v -f --wheel-args="-r {1}" --keep-wheels'
            .format(TEST_PACKAGE, reqs_file_path))
        metadata = self._test(result=result, expected_number_of_wheels=6)
        assert metadata['package_source'] == TEST_PACKAGE
        assert 'virtualenv-13.1.2-py2.py3-none-any.whl' in metadata['wheels']
        os.close(fd)

    def test_create_archive_in_destination_dir_from_pypi_latest(self):
        temp_dir = tempfile.mkdtemp()
        shutil.rmtree(temp_dir)
        package = 'wheel'
        try:
            self.platform = 'any'
            pypi_version = \
                wagon._get_package_info_from_pypi(package)['version']
            self.archive_name = \
                wagon._set_archive_name(
                    package,
                    pypi_version,
                    self.python_versions,
                    self.platform)
            result = _invoke('wagon create {0} -v -f -o {1}'.format(
                package, temp_dir))
            assert result.returncode == 0
            metadata = wagon.show(os.path.join(temp_dir, self.archive_name))
            self.platform = 'linux_x86_64'
            assert pypi_version == metadata['package_version']
        finally:
            shutil.rmtree(temp_dir)

    def test_create_with_requirements(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        requirement_files = [os.path.join(test_package, 'requirements.txt')]

        archive_path = wagon.create(
            source=test_package,
            force=True,
            requirement_files=requirement_files)
        self.archive_name = os.path.basename(archive_path)
        self.platform = 'any'
        metadata = wagon.show(self.archive_name)
        wheel_names = [whl.split('-')[0] for whl in metadata['wheels']]
        assert 'wheel' in wheel_names
        assert 'test_package' in wheel_names

    def test_create_archive_from_path_and_validate(self):
        source = wagon.get_source(TEST_TAR)
        fd, requirements_file_path = tempfile.mkstemp()
        os.close(fd)
        with open(requirements_file_path, 'w') as requirements_file:
            requirements_file.write('wheel')
        result = _invoke(
            'wagon create {0} -v -f --validate --wheel-args="-r {1}"'
            .format(source, requirements_file_path))
        try:
            python_version = sys.version_info
            if python_version[0] == 3:
                expected_number_of_wheels = 6
            elif python_version[0] == 2 and python_version[1] == 7:
                expected_number_of_wheels = 6
            elif python_version[0] == 2 and python_version[1] == 6:
                expected_number_of_wheels = 7
            metadata = self._test(
                result=result,
                expected_number_of_wheels=expected_number_of_wheels)
        finally:
            os.remove(requirements_file_path)
        assert metadata['package_source'] == source
        assert any(
            whl for whl in metadata['wheels'] if whl.startswith('wheel'))

    def test_create_archive_already_exists(self):
        wagon.create(TEST_PACKAGE)
        assert os.path.isfile(self.archive_name)
        with pytest.raises(wagon.WagonError) as ex:
            wagon.create(TEST_PACKAGE)
        assert 'Destination archive already exists:' in str(ex)

    def test_create_archive_already_exists_force(self):
        wagon.create(TEST_PACKAGE)
        assert os.path.isfile(self.archive_name)
        wagon.create(TEST_PACKAGE, force=True)
        assert os.path.isfile(self.archive_name)

    def test_fail_create(self):
        with pytest.raises(SystemExit) as ex:
            _parse('wagon create non_existing_package -v -f')
        assert 'Failed to retrieve info for package' in str(ex)


class TestInstall:

    def setup_method(self, test_method):
        wagon._run('virtualenv test_env')
        self.archive_path = wagon.create(
            source=TEST_PACKAGE,
            force=True)

    def teardown_method(self, test_method):
        os.remove(self.archive_path)
        if os.path.isdir('test_env'):
            shutil.rmtree('test_env')

    # TODO: Important before releasing 0.6.0!
    @pytest.mark.skipif(not os.environ.get('CI'),
                        reason='Can only run in CI env')
    def test_install_package_from_local_archive(self):
        assert not wagon._check_installed(TEST_PACKAGE_NAME)
        _parse("wagon install {0} -v -u".format(self.archive_path))
        assert wagon._check_installed(TEST_PACKAGE_NAME)

    def test_fail_install(self):
        result = _invoke("wagon install non_existing_archive -v -u")
        assert result.returncode == 1

    @mock.patch('wagon.get_platform', return_value='weird_platform')
    def test_fail_install_unsupported_platform(self, _):
        with pytest.raises(SystemExit) as ex:
            _parse("wagon install {0} -v -u".format(self.archive_path))
        assert 'Platform unsupported for package (weird_platform)' in str(ex)


class TestValidate:
    def setup_method(self, test_method):
        self.archive_path = wagon.create(source=TEST_PACKAGE)

    def teardown_method(self, test_method):
        if os.path.isfile(self.archive_path):
            os.remove(self.archive_path)

    def test_validate_package(self):
        result = _invoke('wagon validate {0} -v'.format(self.archive_path))
        assert result.returncode == 0

    def test_fail_validate_invalid_wagon(self):
        fd, invalid_wagon = tempfile.mkstemp()
        os.close(fd)
        # In python2.6, an empty file can be opened as a tar archive.
        # We fill it up so that it fails.
        with open(invalid_wagon, 'w') as f:
            f.write('something')

        try:
            with pytest.raises(SystemExit) as ex:
                _parse('wagon validate {0}'.format(invalid_wagon))
            assert 'Failed to extract {0}'.format(invalid_wagon) in str(ex)
        finally:
            os.remove(invalid_wagon)

    @mock.patch('wagon._check_installed', return_value=False)
    def test_fail_validate_package_not_installed(self, _):
        result = wagon.validate(self.archive_path)
        assert 'failed to install' in result[0]
        assert len(result) == 1

    def test_fail_validation_exclude_and_missing_wheel(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        requirement_files = [os.path.join(test_package, 'requirements.txt')]
        archive_path = wagon.create(source=test_package,
                                    requirement_files=requirement_files,
                                    force=True)
        archive_name = os.path.basename(archive_path)
        tempdir = tempfile.mkdtemp()
        try:
            wagon._untar(archive_name, tempdir)
            wheels_dir = os.path.join(
                tempdir, 'test-package', wagon.DEFAULT_WHEELS_PATH)
            for wheel in os.listdir(wheels_dir):
                if wheel.startswith('wheel'):
                    break
            wheel_to_delete = os.path.join(wheels_dir, wheel)
            os.remove(wheel_to_delete)
            wagon._tar(
                os.path.join(tempdir, 'test-package'), archive_name)
            result = wagon.validate(archive_name)
            assert len(result) == 1
        finally:
            shutil.rmtree(tempdir)
            if os.path.isfile(archive_name):
                os.remove(archive_name)


class TestShowMetadata:
    def setup_method(self, test_method):
        self.archive_path = wagon.create(source=TEST_PACKAGE, force=True)
        wagon._untar(self.archive_path, '.')
        self.expected_metadata = wagon._get_metadata(TEST_PACKAGE_NAME)

    def teardown_method(self, test_method):
        os.remove(self.archive_path)
        shutil.rmtree(TEST_PACKAGE_NAME)

    def test_show_metadata_for_archive(self):
        # merely invoke it directly for coverage sake
        _parse('wagon show {0}'.format(self.archive_path))
        result = _invoke('wagon show {0}'.format(self.archive_path))
        assert result.returncode == 0
        # Remove the first line
        resulting_metadata = json.loads(result.stdout)
        assert resulting_metadata == self.expected_metadata

    def test_fail_show_metadata_for_non_existing_archive(self):
        with pytest.raises(SystemExit) as ex:
            _parse('wagon show non_existing_archive')
        assert 'Failed to retrieve info for package' in str(ex)
