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
from contextlib import closing

import mock
import testtools
import virtualenv  # NOQA
import click.testing as clicktest

import wagon


TEST_TAR = 'https://github.com/pallets/flask/archive/0.10.1.tar.gz'  # NOQA
TEST_ZIP = 'https://github.com/pallets/flask/archive/0.10.1.zip'  # NOQA
TEST_PACKAGE_NAME = 'Flask'
TEST_PACKAGE_VERSION = '0.10.1'
TEST_PACKAGE_PLATFORM = 'linux_x86_64'
TEST_PACKAGE = '{0}=={1}'.format(TEST_PACKAGE_NAME, TEST_PACKAGE_VERSION)


def _invoke_click(func, args=None, opts=None):

    args = args or []
    opts = opts or {}
    opts_and_args = []
    opts_and_args.extend(args)
    for opt, value in opts.items():
        if value:
            opts_and_args.append(opt + value)
        else:
            opts_and_args.append(opt)
    return clicktest.CliRunner().invoke(getattr(wagon, func), opts_and_args)


class TestBase(testtools.TestCase):

    def test_run(self):
        proc = wagon.run('uname')
        self.assertEqual(0, proc.returncode)

    def test_run_bad_command(self):
        proc = wagon.run('suname')
        self.assertEqual(1 if wagon.IS_WIN else 127, proc.returncode)

    def test_download_file(self):
        wagon._download_file(TEST_TAR, 'file')
        try:
            os.remove('file')
        except:
            self.fail()

    def test_download_file_missing(self):
        e = self.assertRaises(
            IOError,
            wagon._download_file,
            'http://www.google.com/x.tar.gz',
            'file')
        self.assertIn("'http error', 404, 'Not Found'", str(e))

    def test_download_bad_url(self):
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
        self.assertIn('No such file or directory', e)

    def test_download_no_permissions(self):
        if wagon.IS_WIN:
            self.skipTest('Irrelevant on Windows.')
        e = self.assertRaises(IOError, wagon._download_file, TEST_TAR, '/file')
        self.assertIn('Permission denied', str(e))

    def test_tar(self):
        os.makedirs('dir')
        with open('dir/content.file', 'w') as f:
            f.write('CONTENT')
        wagon._tar('dir', 'tar.file')
        shutil.rmtree('dir')
        self.assertTrue(tarfile.is_tarfile('tar.file'))
        with closing(tarfile.open('tar.file', 'r:gz')) as tar:
            members = tar.getnames()
            self.assertIn('dir/content.file', members)
        os.remove('tar.file')

    def test_tar_no_permissions(self):
        if wagon.IS_WIN:
            self.skipTest("Irrelevant on Windows.")
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

    def test_make_virtualenv_illegal_dir(self):
        if wagon.IS_WIN:
            self.skipTest('Irrelevant on Windows')
        illegal_path = '/opt/test_virtualenv'
        ex = self.assertRaises(
            wagon.WagonError,
            wagon._make_virtualenv,
            illegal_path)
        self.assertIn('Could not create virtualenv', str(ex))

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
        wagon._make_virtualenv('test_env')
        try:
            result = wagon._check_installed(TEST_PACKAGE_NAME, 'test_env')
            self.assertFalse(result)
        finally:
            shutil.rmtree('test_env')

    def test_install_package_failed(self):
        e = self.assertRaises(
            wagon.WagonError, wagon.install_package, 'x', 'y')
        self.assertIn('Could not install package:', str(e))

    def test_archive_unsupported_format(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon._create_wagon_archive,
            'unsupported_format',
            'source_dir',
            'output_archive')
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

    @mock.patch('sys.executable', new='/a/b/c/python')
    def test_pip_path_on_linux(self):
        if wagon.IS_WIN:
            self.skipTest('Irrelevant on Windows')
        self.assertEqual(wagon._get_pip_path(virtualenv=''), '/a/b/c/pip')

    @mock.patch('sys.executable',
                new='C:\Python27\python.exe')
    def test_pip_path_on_windows(self):
        if wagon.IS_LINUX:
            self.skipTest('Irrelevant on Linux')
        self.assertEqual(wagon._get_pip_path(virtualenv=''),
                         'C:\Python27\scripts\pip.exe')


class TestGetSource(testtools.TestCase):
    def test_source_file_not_a_valid_archive(self):
        fd, source_input = tempfile.mkstemp()
        os.close(fd)
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

    # def test_source_file_not_a_package_archive(self):
    #     package_dir = tempfile.mkdtemp()
    #     fd, source_input = tempfile.mkstemp()
    #     os.close(fd)
    #     wagon._tar(package_dir, source_input)

    #     try:
    #         instance = wagon.Wagon(source_input)
    #         ex = self.assertRaises(
    #             wagon.WagonError,
    #             instance.get_source,
    #             source_input)
    #         self.assertIn(
    #             'Source does not seem to be a Python package',
    #             str(ex))
    #     finally:
    #         shutil.rmtree(package_dir)
    #         os.remove(source_input)

    def test_source_directory_not_a_package(self):
        source_input = tempfile.mkdtemp()

        try:
            ex = self.assertRaises(
                wagon.WagonError,
                wagon.get_source,
                source_input)
            self.assertIn(
                'Source directory must contain a setup.py file',
                str(ex))
        finally:
            shutil.rmtree(source_input)

    def test_source_pypi_no_version(self):
        source_input = TEST_PACKAGE_NAME
        source_output, _ = wagon.get_source(source_input)
        self.assertEqual(
            source_output,
            wagon._get_package_info_from_pypi(TEST_PACKAGE_NAME)['name'])

    def test_source_pypi_with_version(self):
        source_input = TEST_PACKAGE
        source_output, _ = wagon.get_source(source_input)
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
        self.assertEqual(result.exit_code, 0)
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
        if hasattr(self, 'excluded_package'):
            self.assertEqual(
                len(metadata['wheels']),
                4)
        else:
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
        params = {
            '-v': None,
            '-f': None,
        }
        result = _invoke_click('create_wagon', [TEST_PACKAGE], params)
        metadata = self._test(result)
        self.assertEqual(metadata['package_source'], TEST_PACKAGE)

    def test_create_zip_formatted_wagon_from_zip(self):
        self.archive_name = wagon._set_archive_name(
            TEST_PACKAGE_NAME,
            TEST_PACKAGE_VERSION,
            self.python_versions,
            self.platform)
        params = {
            '-v': None,
            '-f': None,
            '-t': 'zip'
        }
        result = _invoke_click('create_wagon', [TEST_ZIP], params)
        metadata = self._test(result)
        self.assertEqual(metadata['package_source'], TEST_ZIP)

    def test_create_archive_from_pypi_with_additional_wheel_args(self):
        fd, reqs_file_path = tempfile.mkstemp()
        os.write(fd, 'virtualenv==13.1.2')
        params = {
            '-v': None,
            '-f': None,
            '-a': '-r {0}'.format(reqs_file_path),
            '--keep-wheels': None
        }
        result = _invoke_click('create_wagon', [TEST_PACKAGE], params)
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
        params = {
            '-v': None,
            '-f': None,
            '-o': temp_dir
        }
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
            result = _invoke_click('create_wagon', [package], params)
            self.assertEqual(result.exit_code, 0)
            metadata = wagon.show(os.path.join(temp_dir, self.archive_name))
            self.platform = 'linux_x86_64'
            self.assertEqual(pypi_version, metadata['package_version'])
        finally:
            shutil.rmtree(temp_dir)

    def test_create_with_requirements(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        archive_path = wagon.create(
            source=test_package,
            force=True,
            with_requirements=True,
            verbose=True)
        self.archive_name = os.path.basename(archive_path)
        self.platform = 'any'
        metadata = wagon.show(self.archive_name)
        wheel_names = [whl.split('-')[0] for whl in metadata['wheels']]
        self.assertIn('wheel', wheel_names)
        self.assertIn('test_package', wheel_names)

    def test_create_archive_from_url_with_requirements(self):
        if wagon.IS_WIN:
            self.skipTest('Due to a certificate related problem with AppVeyor '
                          'we currently have to ignore this test on Windows.')
        # once appveyor's problem is fixed, this will be used.
        self.platform = 'win32' if wagon.IS_WIN else wagon.get_platform()
        self.archive_name = wagon._set_archive_name(
            TEST_PACKAGE_NAME,
            TEST_PACKAGE_VERSION,
            self.python_versions,
            self.platform)
        params = {
            '-v': None,
            '-f': None,
            '-r': None
        }
        result = _invoke_click('create_wagon', [TEST_TAR], params)
        metadata = self._test(result)
        self.assertEqual(metadata['package_source'], TEST_TAR)

    def test_create_archive_from_path_and_validate(self):
        source, _ = wagon.get_source(TEST_TAR)
        fd, requirements_file_path = tempfile.mkstemp()
        os.close(fd)
        with open(requirements_file_path, 'w') as requirements_file:
            requirements_file.write('wheel')
        params = {
            '-v': None,
            '-f': None,
            '--validate': None,
            '-a': '-r {0}'.format(requirements_file_path)
        }
        result = _invoke_click('create_wagon', [source], params)
        try:
            python_version = sys.version_info
            if python_version[0] == 2 and python_version[1] == 7:
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

    def test_create_archive_with_exclusion(self):
        self.excluded_package = 'Jinja2'
        params = {
            '-v': None,
            '-f': None,
            '-x': self.excluded_package
        }
        result = _invoke_click('create_wagon', [TEST_PACKAGE], params)
        metadata = self._test(result)
        self.assertEqual(len(metadata['excluded_wheels']), 1)

    def test_create_archive_with_missing_exclusion(self):
        self.missing_excluded_package = 'non_existing_package'
        params = {
            '-v': None,
            '-f': None,
            '-x': self.missing_excluded_package
        }
        result = _invoke_click('create_wagon', [TEST_PACKAGE], params)
        metadata = self._test(result)
        self.assertEqual(len(metadata['excluded_wheels']), 0)

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

    def test_create_while_excluding_the_main_package(self):
        e = self.assertRaises(
            wagon.WagonError,
            wagon.create,
            source=TEST_PACKAGE,
            excluded_packages=[TEST_PACKAGE_NAME])
        self.assertIn(
            'You cannot exclude the package you are trying to wheel.',
            str(e))

    def test_fail_create(self):
        params = {
            '-v': None,
            '-f': None,
        }
        result = _invoke_click(
            'create_wagon', ['non_existing_package'], params)
        self.assertEqual(result.exit_code, 1)


class TestInstall(testtools.TestCase):

    def setUp(self):
        super(TestInstall, self).setUp()
        wagon.run('virtualenv test_env')
        self.archive_path = wagon.create(
            source=TEST_PACKAGE,
            force=True,
            verbose=True)

    def tearDown(self):
        super(TestInstall, self).tearDown()
        os.remove(self.archive_path)
        if os.path.isdir('test_env'):
            shutil.rmtree('test_env')

    def test_install_package_from_local_archive(self):
        params = {
            '-v': None,
            '--virtualenv=': 'test_env',
            '-u': None,
            '-a': '--retries 2'
        }
        _invoke_click('install_wagon', [self.archive_path], params)
        self.assertTrue(wagon._check_installed(TEST_PACKAGE_NAME, 'test_env'))

    def test_fail_install(self):
        params = {
            '-v': None,
            '--virtualenv=': 'non_existing_env',
            '-u': None,
            '-a': '--retries 2'
        }
        result = _invoke_click('install_wagon', [self.archive_path], params)
        self.assertEqual(result.exit_code, 1)

    @mock.patch('wagon.get_platform', return_value='weird_platform')
    def test_fail_install_unsupported_platform(self, _):
        params = {
            '-v': None,
            '--virtualenv=': 'non_existing_env',
            '-u': None,
            '-a': '--retries 2'
        }
        result = _invoke_click('install_wagon', [self.archive_path], params)
        self.assertEqual(result.exit_code, 1)


class TestValidate(testtools.TestCase):

    def setUp(self):
        super(TestValidate, self).setUp()
        self.archive_path = wagon.create(source=TEST_PACKAGE)

    def tearDown(self):
        super(TestValidate, self).tearDown()
        if os.path.isfile(self.archive_path):
            os.remove(self.archive_path)

    def test_validate_package(self):
        params = {'-v': None}
        result = _invoke_click('validate_wagon', [self.archive_path], params)
        self.assertEqual(result.exit_code, 0)

    def test_fail_validate_invalid_wagon(self):
        fd, temp_invalid_wagon = tempfile.mkstemp()
        os.close(fd)
        with open(temp_invalid_wagon, 'w') as f:
            f.write('something')

        try:
            result = _invoke_click('validate_wagon', [temp_invalid_wagon])
            self.assertEqual(result.exit_code, 1)
        finally:
            os.remove(temp_invalid_wagon)

    @mock.patch('wagon._check_installed', return_value=False)
    def test_fail_validate_package_not_installed(self, _):
        result = _invoke_click('validate_wagon', [self.archive_path])
        self.assertEqual(result.exit_code, 1)

    def test_fail_validation_exclude_and_missing_wheel(self):
        test_package = os.path.join('tests', 'resources', 'test-package')
        archive_path = wagon.create(source=test_package,
                                    with_requirements=True,
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
        self.metadata = wagon._get_metadata(TEST_PACKAGE_NAME)

    def tearDown(self):
        super(TestShowMetadata, self).tearDown()
        os.remove(self.archive_path)

    def test_show_metadata_for_archive(self):
        result = _invoke_click('show_wagon', [self.archive_path])
        self.assertEqual(result.exit_code, 0)
        self.assertDictEqual(json.loads(result.output), self.metadata)

    def test_fail_show_metadata_for_non_existing_archive(self):
        result = _invoke_click('show_wagon', ['non_existing_archive'])
        self.assertEqual(result.exit_code, 1)


# # TODO: move all test artifacts to non-cwd paths
