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
import testtools
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


class TestBase(testtools.TestCase):

    def test_run(self):
        proc = wagon._run('uname')
        self.assertEqual(0, proc.returncode)

    def test_run_bad_command(self):
        proc = wagon._run('suname')
        self.assertEqual(1 if wagon.IS_WIN else 127, proc.returncode)

    def test_download_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        wagon._download_file(TEST_TAR, path)
        try:
            os.remove(path)
        except:
            self.fail()

    def test_download_file_missing(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon._download_file,
            'http://www.google.com/x.tar.gz',
            'file')
        self.assertIn("Failed to download file", str(e))

    def test_download_bad_url(self):
        if IS_PY3:
            e = self.assertRaises(
                ValueError, wagon._download_file, 'something', 'file')
            self.assertIn("unknown url type: 'something'", str(e))
        else:
            e = self.assertRaises(
                IOError, wagon._download_file, 'something', 'file')
            if wagon.IS_WIN:
                self.assertIn(
                    "The system cannot find the file specified: 'something'",
                    str(e))
            else:
                self.assertIn("No such file or directory: 'something'", str(e))

    def test_download_missing_path(self):
        e = self.assertRaises(
            IOError, wagon._download_file, TEST_TAR, 'x/file')
        self.assertIn('No such file or directory', str(e))

    @testtools.skipIf(wagon.IS_WIN, 'Irrelevant on Windows.')
    def test_download_no_permissions(self):
        e = self.assertRaises(IOError, wagon._download_file, TEST_TAR, '/file')
        self.assertIn('Permission denied', str(e))

    def test_tar(self):
        tempdir = tempfile.mkdtemp()
        with open(os.path.join(tempdir, 'content.file'), 'w') as f:
            f.write('CONTENT')
        wagon._tar(tempdir, 'tar.file')
        shutil.rmtree(tempdir)
        self.assertTrue(tarfile.is_tarfile('tar.file'))
        with closing(tarfile.open('tar.file', 'r:gz')) as tar:
            members = tar.getnames()
            dirname = os.path.split(tempdir)[1]
            self.assertIn('{0}/content.file'.format(dirname), members)
        os.remove('tar.file')

    @testtools.skipIf(wagon.IS_WIN, 'Irrelevant on Windows.')
    def test_tar_no_permissions(self):
        tmpdir = tempfile.mkdtemp()
        try:
            e = self.assertRaises(IOError, wagon._tar, tmpdir, '/file')
            self.assertIn("Permission denied: '/file'", str(e))
        finally:
            shutil.rmtree(tmpdir)

    def test_tar_missing_source(self):
        e = self.assertRaises(OSError, wagon._tar, 'missing', 'file')
        if wagon.IS_WIN:
            self.assertIn(
                "The system cannot find the file specified: 'missing'",
                str(e))
        else:
            self.assertIn("No such file or directory: 'missing'", str(e))
        os.remove('file')

    def test_make_virtualenv(self):
        virtualenv_path = wagon._make_virtualenv()
        try:
            pip_path = wagon._get_pip_path(virtualenv_path)
            self.assertTrue(os.path.isfile(pip_path))
        finally:
            shutil.rmtree(virtualenv_path)

    def test_wheel_nonexisting_package(self):
        try:
            e = self.assertRaises(
                wagon.WagonError, wagon.wheel, 'cloudify-script-plug==1.3')
            self.assertIn('Could not download wheels for:', str(e))
        finally:
            shutil.rmtree('package')

    def test_machine_platform(self):
        self.assertIn(
            'win32' if wagon.IS_WIN else 'linux_x86_64',
            wagon.get_platform())

    def test_get_version_from_pypi_bad_source(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon._get_package_info_from_pypi,
            'NONEXISTING_PACKAGE')
        self.assertIn('Failed to retrieve info for package', str(e))

    def test_check_package_not_installed(self):
        virtualenv_path = wagon._make_virtualenv()
        try:
            result = wagon._check_installed(TEST_PACKAGE_NAME, virtualenv_path)
            self.assertFalse(result)
        finally:
            shutil.rmtree(virtualenv_path)

    def test_install_package_failed(self):
        e = self.assertRaises(
            wagon.WagonError, wagon.install_package, 'x', 'y')
        self.assertIn('Could not install package:', str(e))

    def test_archive_unsupported_format(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon._create_wagon_archive,
            'source_dir',
            'output_archive',
            'unsupported_format')
        self.assertIn('Unsupported archive format to create', str(e))

    def test_single_python_version(self):
        versions = wagon._set_python_versions()
        verinfo = sys.version_info
        version = ['py{0}{1}'.format(verinfo[0], verinfo[1])]
        self.assertEqual(versions, version)

    def test_provided_python_version(self):
        provided_version_numbers = ['27', '26']
        versions = wagon._set_python_versions(provided_version_numbers)
        expected_versions = ['py27', 'py26']
        self.assertEqual(versions, expected_versions)

    @testtools.skipIf(wagon.IS_WIN, 'Irrelevant on Windows.')
    @mock.patch('sys.executable', new='/a/b/c/python')
    def test_pip_path_on_linux(self):
        self.assertEqual(wagon._get_pip_path(venv=''), '/a/b/c/pip')

    @testtools.skipIf(not wagon.IS_WIN, 'Irrelevant on Linux.')
    @mock.patch('sys.executable', new='C:\Python27\python.exe')
    def test_pip_path_on_windows(self):
        self.assertEqual(wagon._get_pip_path(venv=''),
                         'C:\Python27\scripts\pip.exe')

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
            self.assertIn(temp_wheel_filename, wheels)
            self.assertNotIn(temp_non_wheel_filename, wheels)
        finally:
            shutil.rmtree(tempdir)

    def test_cli_too_few_arguments(self):
        ex = self.assertRaises(
            SystemExit,
            _parse,
            'wagon create')
        if wagon.IS_PY3:
            self.assertIn('the following arguments are required', str(ex))
        else:
            self.assertIn('too few arguments', str(ex))

    def test_cli_bad_arumgnet(self):
        ex = self.assertRaises(
            SystemExit,
            _parse,
            'wagon create flask --non-existing-argument')
        self.assertIn(
            'error: unrecognized arguments: --non-existing-argument',
            str(ex))


class TestGetSource(testtools.TestCase):
    def test_source_file_not_a_valid_archive(self):
        fd, source_input = tempfile.mkstemp()
        os.close(fd)
        # In python2.6, an empty file can be opened as a tar archive.
        # We fill it up so that it fails.
        with open(source_input, 'w') as f:
            f.write('something')

        try:
            ex = self.assertRaises(
                wagon.WagonError,
                wagon.get_source,
                source_input)
            self.assertIn('Failed to extract', str(ex))
        finally:
            os.remove(source_input)

    def test_source_directory_not_a_package(self):
        source_input = tempfile.mkdtemp()

        try:
            ex = self.assertRaises(
                wagon.WagonError,
                wagon.create,
                source_input)
            self.assertIn(
                'Source directory must contain a setup.py file',
                str(ex))
        finally:
            shutil.rmtree(source_input)

    def test_source_pypi_no_version(self):
        source_input = TEST_PACKAGE_NAME
        source_output = wagon.get_source(source_input)
        self.assertEqual(
            source_output,
            wagon._get_package_info_from_pypi(TEST_PACKAGE_NAME)['name'])

    def test_source_pypi_with_version(self):
        source_input = TEST_PACKAGE
        source_output = wagon.get_source(source_input)
        test_package = '{0}=={1}'.format(
            wagon._get_package_info_from_pypi(TEST_PACKAGE_NAME)['name'],
            TEST_PACKAGE_VERSION)
        self.assertEqual(
            source_output,
            test_package)


class TestCreateBadSources(testtools.TestCase):
    def test_unsupported_url_schema(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon.create,
            source='ftp://x')
        self.assertIn('Source URL type', str(e))


class TestCreate(testtools.TestCase):

    def setUp(self):
        super(TestCreate, self).setUp()
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

    def tearDown(self):
        super(TestCreate, self).tearDown()
        if os.path.isfile(self.archive_name):
            os.remove(self.archive_name)
        if os.path.isdir(self.package_name):
            shutil.rmtree(self.package_name)

    def _test(self, result, expected_number_of_wheels=5):
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.isfile(self.archive_name))

        try:
            wagon._untar(self.archive_name, '.')
        except:
            wagon._unzip(self.archive_name, '.')
        with open(os.path.join(
                self.package_name,
                wagon.METADATA_FILE_NAME)) as f:
            metadata = json.loads(f.read())

        self.assertEqual(
            self.wagon_version,
            metadata['created_by_wagon_version'])
        self.assertEqual(
            self.package_version,
            metadata['package_version'])
        self.assertEqual(
            self.package_name,
            metadata['package_name'])
        self.assertEqual(
            self.platform,
            metadata['supported_platform'])
        self.assertEqual(
            len(metadata['wheels']),
            expected_number_of_wheels)

        if wagon.IS_LINUX and self.platform != 'any':
            distro, version, release = wagon._get_os_properties()
            self.assertEqual(
                distro.lower(),
                metadata['build_server_os_properties']['distribution'])
            self.assertEqual(
                version.lower(),
                metadata['build_server_os_properties']['distribution_version'])
            self.assertEqual(
                release.lower(),
                metadata['build_server_os_properties']['distribution_release'])

        self.assertIn(
            '{0}-{1}-{2}-none-{3}'.format(
                self.package_name.replace('-', '_'),
                self.package_version,
                '.'.join(self.python_versions),
                self.platform),
            metadata['archive_name'])

        return metadata

    def test_create_archive_from_pypi_with_version(self):
        result = _invoke('wagon create {0} -v -f '.format(TEST_PACKAGE))
        metadata = self._test(result)
        self.assertEqual(metadata['package_source'], TEST_PACKAGE)

    def test_create_zip_formatted_wagon_from_zip(self):
        self.archive_name = wagon._set_archive_name(
            TEST_PACKAGE_NAME,
            TEST_PACKAGE_VERSION,
            self.python_versions,
            self.platform)
        result = _invoke('wagon create {0} -v -f -t zip'.format(TEST_ZIP))
        metadata = self._test(result)
        self.assertEqual(metadata['package_source'], TEST_ZIP)

    def test_create_archive_from_pypi_with_additional_wheel_args(self):
        fd, reqs_file_path = tempfile.mkstemp()
        os.write(fd, b'virtualenv==13.1.2')
        result = _invoke(
            'wagon create {0} -v -f --wheel-args="-r {1}" --keep-wheels'
            .format(TEST_PACKAGE, reqs_file_path))
        metadata = self._test(
            result=result,
            expected_number_of_wheels=6)
        self.assertEqual(metadata['package_source'], TEST_PACKAGE)
        self.assertIn(
            'virtualenv-13.1.2-py2.py3-none-any.whl',
            metadata['wheels'])
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
            self.assertEqual(result.returncode, 0)
            metadata = wagon.show(os.path.join(temp_dir, self.archive_name))
            self.platform = 'linux_x86_64'
            self.assertEqual(pypi_version, metadata['package_version'])
        finally:
            shutil.rmtree(temp_dir)

    def test_create_with_requirements(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        requirement_files = [os.path.join(test_package, 'requirements.txt')]

        archive_path = wagon.create(
            source=test_package,
            force=True,
            requirement_files=requirement_files,
            verbose=True)
        self.archive_name = os.path.basename(archive_path)
        self.platform = 'any'
        metadata = wagon.show(self.archive_name)
        wheel_names = [whl.split('-')[0] for whl in metadata['wheels']]
        self.assertIn('wheel', wheel_names)
        self.assertIn('test_package', wheel_names)

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
        self.assertEqual(metadata['package_source'], source)
        self.assertTrue(any(
            whl for whl in metadata['wheels'] if whl.startswith('wheel')))

    def test_create_archive_already_exists(self):
        wagon.create(TEST_PACKAGE)
        self.assertTrue(os.path.isfile(self.archive_name))
        e = self.assertRaises(
            wagon.WagonError,
            wagon.create,
            TEST_PACKAGE)
        self.assertIn('Destination archive already exists:', str(e))

    def test_create_archive_already_exists_force(self):
        wagon.create(TEST_PACKAGE)
        self.assertTrue(os.path.isfile(self.archive_name))
        wagon.create(TEST_PACKAGE, force=True)
        self.assertTrue(os.path.isfile(self.archive_name))

    def test_fail_create(self):
        ex = self.assertRaises(
            SystemExit,
            _parse,
            'wagon create non_existing_package -v -f')
        self.assertIn('Failed to retrieve info for package', str(ex))


class TestInstall(testtools.TestCase):

    def setUp(self):
        super(TestInstall, self).setUp()
        wagon._run('virtualenv test_env')
        self.archive_path = wagon.create(
            source=TEST_PACKAGE,
            force=True,
            verbose=True)

    def tearDown(self):
        super(TestInstall, self).tearDown()
        os.remove(self.archive_path)
        if os.path.isdir('test_env'):
            shutil.rmtree('test_env')

    # TODO: Important before releasing 0.6.0!
    @testtools.skipIf(wagon.IS_WIN, 'UNKNOWN PROBLEM! NEED TO FIX!.')
    def test_install_package_from_local_archive(self):
        self.assertFalse(wagon._check_installed(TEST_PACKAGE_NAME))
        _parse("wagon install {0} -v -u".format(self.archive_path))
        self.assertTrue(wagon._check_installed(TEST_PACKAGE_NAME))

    def test_fail_install(self):
        result = _invoke("wagon install non_existing_archive -v -u")
        self.assertEqual(result.returncode, 1)

    @mock.patch('wagon.get_platform', return_value='weird_platform')
    def test_fail_install_unsupported_platform(self, _):
        try:
            _parse("wagon install {0} -v -u".format(self.archive_path))
        except SystemExit as ex:
            self.assertEqual(
                'Platform unsupported for package (weird_platform)',
                str(ex))


class TestValidate(testtools.TestCase):

    def setUp(self):
        super(TestValidate, self).setUp()
        self.archive_path = wagon.create(source=TEST_PACKAGE)

    def tearDown(self):
        super(TestValidate, self).tearDown()
        if os.path.isfile(self.archive_path):
            os.remove(self.archive_path)

    def test_validate_package(self):
        result = _invoke('wagon validate {0} -v'.format(self.archive_path))
        self.assertEqual(result.returncode, 0)

    def test_fail_validate_invalid_wagon(self):
        fd, invalid_wagon = tempfile.mkstemp()
        os.close(fd)
        # In python2.6, an empty file can be opened as a tar archive.
        # We fill it up so that it fails.
        with open(invalid_wagon, 'w') as f:
            f.write('something')

        try:
            ex = self.assertRaises(
                SystemExit,
                _parse,
                'wagon validate {0}'.format(invalid_wagon))
            self.assertIn('Failed to extract {0}'.format(
                invalid_wagon), str(ex))
        finally:
            os.remove(invalid_wagon)

    @mock.patch('wagon._check_installed', return_value=False)
    def test_fail_validate_package_not_installed(self, _):
        result = wagon.validate(self.archive_path)
        self.assertIn('failed to install', result[0])
        self.assertEqual(len(result), 1)

    def test_fail_validation_exclude_and_missing_wheel(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        requirement_files = [os.path.join(test_package, 'requirements.txt')]
        archive_path = wagon.create(source=test_package,
                                    requirement_files=requirement_files,
                                    force=True,
                                    verbose=True)
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
            self.assertEqual(len(result), 1)
        finally:
            shutil.rmtree(tempdir)
            if os.path.isfile(archive_name):
                os.remove(archive_name)


class TestShowMetadata(testtools.TestCase):
    def setUp(self):
        super(TestShowMetadata, self).setUp()
        self.archive_path = wagon.create(source=TEST_PACKAGE, force=True)
        wagon._untar(self.archive_path, '.')
        self.expected_metadata = wagon._get_metadata(TEST_PACKAGE_NAME)

    def tearDown(self):
        super(TestShowMetadata, self).tearDown()
        os.remove(self.archive_path)
        shutil.rmtree(TEST_PACKAGE_NAME)

    def test_show_metadata_for_archive(self):
        # merely invoke it directly for coverage sake
        _parse('wagon show {0}'.format(self.archive_path))
        result = _invoke('wagon show {0}'.format(self.archive_path))
        self.assertEqual(result.returncode, 0)
        # Remove the first line
        resulting_metadata = json.loads(
            '\n'.join(result.stdout.splitlines()[1:]))
        self.assertDictEqual(resulting_metadata, self.expected_metadata)

    def test_fail_show_metadata_for_non_existing_archive(self):
        ex = self.assertRaises(
            SystemExit,
            _parse,
            'wagon show non_existing_archive')
        self.assertIn('Failed to retrieve info for package', str(ex))
