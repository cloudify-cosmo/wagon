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

import click.testing as clicktest
from contextlib import closing
import tarfile
import testtools
import os
import json
import shutil
import tempfile

import wagon.wagon as wagon
import wagon.utils as utils
import wagon.codes as codes


TEST_FILE = 'https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.tar.gz'  # NOQA
TEST_ZIP = 'https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.zip'  # NOQA
TEST_PACKAGE_NAME = 'cloudify-script-plugin'
TEST_PACKAGE_VERSION = '1.2'
TEST_PACKAGE = '{0}=={1}'.format(TEST_PACKAGE_NAME, TEST_PACKAGE_VERSION)


def _invoke_click(func, args_dict):

    args_dict = args_dict or {}
    args_list = []
    for arg, value in args_dict.items():
        if value:
            args_list.append(arg + value)
        else:
            args_list.append(arg)

    return clicktest.CliRunner().invoke(getattr(wagon, func), args_list)


class TestUtils(testtools.TestCase):

    def test_run(self):
        p = utils.run('uname')
        self.assertEqual(0, p.returncode)

    def test_run_bad_command(self):
        p = utils.run('suname')
        self.assertEqual(1 if utils.IS_WIN else 127, p.returncode)

    def test_download_file(self):
        utils.download_file(TEST_FILE, 'file')
        os.remove('file')

    def test_download_file_missing(self):
        e = self.assertRaises(
            IOError, utils.download_file,
            'http://www.google.com/x.tar.gz', 'file')
        self.assertIn("'http error', 404, 'Not Found'", str(e))

    def test_download_bad_url(self):
        e = self.assertRaises(
            IOError, utils.download_file, 'something', 'file')
        if utils.IS_WIN:
            self.assertIn("The system cannot find the file "
                          "specified: 'something'", str(e))
        else:
            self.assertIn("No such file or directory: 'something'", str(e))

    def test_download_missing_path(self):
        e = self.assertRaises(
            IOError, utils.download_file, TEST_FILE, 'x/file')
        self.assertIn('No such file or directory', e)

    def test_download_no_permissions(self):
        if utils.IS_WIN:
            self.skipTest('Irrelevant on Windows.')
        e = self.assertRaises(IOError, utils.download_file, TEST_FILE, '/file')
        self.assertIn('Permission denied', str(e))

    def test_tar(self):
        os.makedirs('dir')
        with open('dir/content.file', 'w') as f:
            f.write('CONTENT')
        utils.tar('dir', 'tar.file')
        shutil.rmtree('dir')
        self.assertTrue(tarfile.is_tarfile('tar.file'))
        with closing(tarfile.open('tar.file', 'r:gz')) as tar:
            members = tar.getnames()
            self.assertIn('dir/content.file', members)
        os.remove('tar.file')

    def test_tar_no_permissions(self):
        if utils.IS_WIN:
            self.skipTest("Irrelevant on Windows.")
        tmpdir = tempfile.mkdtemp()
        try:
            e = self.assertRaises(IOError, utils.tar, tmpdir, '/file')
            self.assertIn("Permission denied: '/file'", str(e))
        finally:
            shutil.rmtree(tmpdir)

    def test_tar_missing_source(self):
        e = self.assertRaises(OSError, utils.tar, 'missing', 'file')
        if utils.IS_WIN:
            self.assertIn("The system cannot find the "
                          "file specified: 'missing'", str(e))
        else:
            self.assertIn("No such file or directory: 'missing'", str(e))
        os.remove('file')

    def test_wheel_nonexisting_package(self):
        try:
            e = self.assertRaises(
                SystemExit, utils.wheel, 'cloudify-script-plug==1.3')
            self.assertEqual(str(codes.errors['failed_to_wheel']), str(e))
        finally:
            shutil.rmtree('package')

    def test_machine_platform(self):
        self.assertIn(
            'win32' if utils.IS_WIN else 'linux_x86_64', utils.get_platform())

    def test_get_version_from_pypi_bad_source(self):
        e = self.assertRaises(
            SystemExit, utils.get_package_version_from_pypi,
            'NONEXISTING_PACKAGE')
        self.assertEqual(
            str(codes.errors['failed_to_retrieve_index_info']), str(e))

    def test_check_package_not_installed(self):
        utils.make_virtualenv('test_env')
        try:
            result = utils.check_installed(TEST_PACKAGE_NAME, 'test_env')
            self.assertFalse(result)
        finally:
            shutil.rmtree('test_env')

    def test_install_package_failed(self):
        e = self.assertRaises(SystemExit, utils.install_package, 'x', 'y')
        self.assertEqual(
            str(codes.errors['failed_to_install_package']), str(e))


class TestCreateBadSources(testtools.TestCase):
    def test_unsupported_url_schema(self):
        packager = wagon.Wagon(source='ftp://x', verbose=True)
        e = self.assertRaises(SystemExit, packager.create)
        self.assertIn(str(codes.errors['unsupported_url_type']), str(e))


class TestCreate(testtools.TestCase):

    def setUp(self):
        super(TestCreate, self).setUp()
        self.runner = clicktest.CliRunner()
        self.wagon = wagon.Wagon(TEST_PACKAGE, verbose=True)
        self.wagon.platform = 'any'
        self.wagon.python_versions = [utils.get_python_version()]
        self.package_version = TEST_PACKAGE_VERSION
        self.package_name = TEST_PACKAGE_NAME
        self.archive_name = self.wagon.set_archive_name(
            self.package_name, self.package_version)

    def tearDown(self):
        super(TestCreate, self).tearDown()
        if os.path.isfile(self.archive_name):
            os.remove(self.archive_name)
        if os.path.isdir(self.package_name):
            shutil.rmtree(self.package_name)

    def _test(self):
        # self.assertIn(self.archive_name, os.listdir('.'))
        self.assertTrue(os.path.isfile(self.archive_name))
        try:
            utils.untar(self.archive_name, '.')
        except:
            utils.unzip(self.archive_name, '.')
        with open(os.path.join(
                self.package_name,
                wagon.METADATA_FILE_NAME), 'r') as f:
            m = json.loads(f.read())

        self.assertEqual(m['package_version'], self.package_version)
        self.assertEqual(m['package_name'], self.package_name)
        self.assertEqual(m['supported_platform'], self.wagon.platform)
        if hasattr(self, 'excluded_package'):
            self.assertTrue(len(m['wheels']) >= 7)
        else:
            self.assertTrue(len(m['wheels']) >= 8)

        if utils.IS_LINUX and self.wagon.platform != 'any':
            distro, version, release = utils.get_os_properties()
            self.assertEqual(
                m['build_server_os_properties']['distribution'],
                distro.lower())
            self.assertEqual(
                m['build_server_os_properties']['distribution_version'],
                version.lower())
            self.assertEqual(
                m['build_server_os_properties']['distribution_release'],
                release.lower())

        self.assertIn(
            '{0}-{1}-{2}-none-{3}'.format(
                self.package_name.replace('-', '_'),
                self.package_version,
                '.'.join(self.wagon.python_versions),
                self.wagon.platform),
            m['archive_name'])

        self.assertTrue(os.path.isfile(os.path.join(
            self.package_name, wagon.DEFAULT_WHEELS_PATH,
            '{0}-{1}-py2-none-any.whl'.format(
                self.package_name.replace('-', '_'),
                self.package_version))))

        return m

    def test_create_archive_from_pypi_with_version(self):
        params = {
            '-s': TEST_PACKAGE,
            '-v': None,
            '-f': None
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(m['package_source'], TEST_PACKAGE)

    def test_create_zip_from_pypi(self):
        self.archive_name = self.wagon.set_archive_name(
            TEST_PACKAGE_NAME, TEST_PACKAGE_VERSION)
        params = {
            '-s': TEST_ZIP,
            '-v': None,
            '-f': None,
            '-t': 'zip'
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(m['package_source'], TEST_ZIP)

    def test_create_archive_from_pypi_with_additional_wheel_args(self):
        fd, reqs_file_path = tempfile.mkstemp()
        os.write(fd, 'virtualenv==13.1.2')
        params = {
            '-s': TEST_PACKAGE,
            '-v': None,
            '-f': None,
            '-a': '-r {0}'.format(reqs_file_path),
            '--keep-wheels': None
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(m['package_source'], TEST_PACKAGE)
        self.assertIn('virtualenv-13.1.2-py2.py3-none-any.whl', m['wheels'])
        os.close(fd)

    def test_create_archive_from_pypi_latest(self):
        package = 'wheel'
        params = {
            '-s': package,
            '-v': None,
            '-f': None,
            '--validate': None
        }
        pypi_version = utils.get_package_version_from_pypi(package)
        self.archive_name = self.wagon.set_archive_name(package, pypi_version)
        result = _invoke_click('create', params)
        self.assertEqual(str(result), '<Result okay>')
        self.wagon.source = self.archive_name
        metadata = self.wagon.get_metadata_from_archive()
        self.assertEqual(pypi_version, metadata['package_version'])

    def test_create_archive_from_url_with_requirements(self):
        self.wagon.platform = 'win32' if utils.IS_WIN else utils.get_platform()
        self.archive_name = self.wagon.set_archive_name(
            TEST_PACKAGE_NAME, TEST_PACKAGE_VERSION)
        params = {
            '-s': TEST_FILE,
            '-v': None,
            '-f': None,
            '-r': None
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(m['package_source'], TEST_FILE)

    def test_create_archive_from_path_and_validate(self):
        source = self.wagon.get_source(TEST_FILE)
        params = {
            '-s': source,
            '-v': None,
            '-f': None,
            '--validate': None
        }
        _invoke_click('create', params)
        m = self._test()
        self.assertEqual(m['package_source'], source)

    def test_create_archive_with_exclusion(self):
        self.excluded_package = 'cloudify-plugins-common'
        params = {
            '-s': TEST_PACKAGE,
            '-v': None,
            '-f': None,
            '-x': self.excluded_package
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(len(m['excluded_wheels']), 1)

    def test_create_archive_with_missing_exclusion(self):
        self.missing_excluded_package = 'cloudify-plugins-common2'
        params = {
            '-s': TEST_PACKAGE,
            '-v': None,
            '-f': None,
            '-x': self.missing_excluded_package
        }
        result = _invoke_click('create', params)
        self.assertIn('Process complete!', str(result.output))
        m = self._test()
        self.assertEqual(len(m['excluded_wheels']), 0)

    def test_create_archive_already_exists(self):
        self.wagon.create()
        self.assertTrue(os.path.isfile(self.archive_name))
        e = self.assertRaises(SystemExit, self.wagon.create)
        self.assertIn(str(codes.errors['archive_already_exists']), str(e))

    def test_create_archive_already_exists_force(self):
        self.wagon.create()
        self.assertTrue(os.path.isfile(self.archive_name))
        self.wagon.create(force=True)
        self.assertTrue(os.path.isfile(self.archive_name))

    def test_create_archive_directory_already_exists(self):
        self.wagon.create(keep_wheels=True)
        self.assertTrue(os.path.isdir(TEST_PACKAGE_NAME))
        e = self.assertRaises(SystemExit, self.wagon.create)
        self.assertIn(str(codes.errors['directory_already_exists']), str(e))

    def test_create_archive_directory_already_exists_force(self):
        self.wagon.create(keep_wheels=True)
        self.assertTrue(os.path.isdir(TEST_PACKAGE_NAME))
        self.wagon.create(force=True)
        self.assertTrue(os.path.isfile(self.archive_name))

    def test_create_while_excluding_the_main_package(self):
        e = self.assertRaises(
            SystemExit, self.wagon.create,
            excluded_packages=[TEST_PACKAGE_NAME])
        self.assertIn(str(codes.errors['cannot_exclude_main_package']), str(e))


class TestInstall(testtools.TestCase):

    def setUp(self):
        super(TestInstall, self).setUp()
        self.runner = clicktest.CliRunner()
        self.packager = wagon.Wagon(TEST_PACKAGE, verbose=True)
        utils.run('virtualenv test_env')
        self.archive_path = self.packager.create(force=True)

    def tearDown(self):
        super(TestInstall, self).tearDown()
        os.remove(self.archive_path)
        if os.path.isdir('test_env'):
            shutil.rmtree('test_env')

    def test_install_package_from_local_archive(self):
        params = {
            '-s': self.archive_path,
            '-v': None,
            '--virtualenv=': 'test_env',
            '-u': None,
            '-a': '--retries 2'
        }
        _invoke_click('install', params)
        self.assertTrue(utils.check_installed(TEST_PACKAGE_NAME, 'test_env'))


class TestValidate(testtools.TestCase):

    def setUp(self):
        super(TestValidate, self).setUp()
        self.runner = clicktest.CliRunner()
        self.packager = wagon.Wagon(TEST_PACKAGE, verbose=True)
        self.archive_path = self.packager.create(force=True)
        utils.untar(self.archive_path, '.')
        with open(os.path.join(
                TEST_PACKAGE_NAME,
                wagon.METADATA_FILE_NAME), 'r') as f:
            self.m = json.loads(f.read())

    def tearDown(self):
        super(TestValidate, self).tearDown()
        if os.path.isfile(self.archive_path):
            os.remove(self.archive_path)
        if os.path.isdir(TEST_PACKAGE_NAME):
            shutil.rmtree(TEST_PACKAGE_NAME)

    def test_validate_package(self):
        params = {
            '-s': self.archive_path,
            '-v': None
        }
        result = _invoke_click('validate', params)
        self.assertEqual(str(result), '<Result okay>')

    def test_get_metadata_for_archive(self):
        params = {
            '-s': self.archive_path,
        }
        result = _invoke_click('showmeta', params)
        self.assertDictEqual(json.loads(result.output), self.m)
