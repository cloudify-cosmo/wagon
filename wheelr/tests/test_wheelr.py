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

import wheelr.wheelr as wheelr
import wheelr.utils as utils

import click.testing as clicktest
from contextlib import closing
import tarfile
import testtools
import os
import json
import shutil

BASE_DIR = 'cloudify'
TEST_VENV = os.path.join(BASE_DIR, 'env')
TEST_FILE = 'https://github.com/cloudify-cosmo/cloudify-script-plugin/archive/1.2.tar.gz'  # NOQA


class TestUtils(testtools.TestCase):

    def test_run(self):
        p = utils.run('uname')
        self.assertEqual(0, p.returncode)

    def test_run_bad_command(self):
        p = utils.run('suname')
        self.assertEqual(127, p.returncode)

    def test_download_file(self):
        utils.download_file(TEST_FILE, 'file')
        if not os.path.isfile('file'):
            raise Exception('file not downloaded')
        os.remove('file')

    def test_download_file_missing(self):
        e = self.assertRaises(
            IOError, utils.download_file,
            'http://www.google.com/x.tar.gz', 'file')
        self.assertIn("'http error', 404, 'Not Found'", str(e))

    def test_download_bad_url(self):
        e = self.assertRaises(
            IOError, utils.download_file, 'something', 'file')
        self.assertIn("No such file or directory: 'something'", str(e))

    def test_download_missing_path(self):
        e = self.assertRaises(
            IOError, utils.download_file, TEST_FILE, 'x/file')
        self.assertIn('No such file or directory', e)

    def test_download_no_permissions(self):
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
        e = self.assertRaises(IOError, utils.tar, TEST_VENV, '/file')
        self.assertIn("Permission denied: '/file'", str(e))

    def test_tar_missing_source(self):
        e = self.assertRaises(OSError, utils.tar, 'missing', 'file')
        self.assertIn("No such file or directory: 'missing'", str(e))
        os.remove('file')

    def test_wheel_nonexisting_module(self):
        try:
            e = self.assertRaises(
                SystemExit, utils.wheel, 'cloudify-script-plug==1.2')
            self.assertEqual('1', str(e))
        finally:
            shutil.rmtree('plugin')

    # non-windows
    def test_machine_platform(self):
        self.assertEqual(utils.get_machine_platform(), 'linux_x86_64')


class TestCreateBadSources(testtools.TestCase):
    def test_bad_source(self):
        packager = wheelr.Wheelr(source='cloudify', verbose=True)
        e = self.assertRaises(SystemExit, packager.create)
        self.assertIn('1', str(e))

    def test_unsupported_url_schema(self):
        packager = wheelr.Wheelr(source='ftp://x', verbose=True)
        e = self.assertRaises(SystemExit, packager.create)
        self.assertIn('1', str(e))

    def test_nonexisting_path(self):
        packager = wheelr.Wheelr(source='~/nonexisting_path', verbose=True)
        e = self.assertRaises(SystemExit, packager.create)
        self.assertIn('1', str(e))


class TestCreate(testtools.TestCase):

    def setUp(self):
        super(TestCreate, self).setUp()
        self.runner = clicktest.CliRunner()
        self.wheelr = wheelr.Wheelr(
            'cloudify-script-plugin==1.2', verbose=True)
        self.tar_name = self.wheelr.set_tar_name(
            'cloudify-script-plugin', '1.2', 'any')
        self.pyver = utils.get_python_version()
        self.platform = 'any'

    def tearDown(self):
        super(TestCreate, self).tearDown()
        if os.path.isfile(self.tar_name):
            os.remove(self.tar_name)
        if os.path.isdir('cloudify-script-plugin'):
            shutil.rmtree('cloudify-script-plugin')

    def _test(self):
        self.assertTrue(os.path.isfile(self.tar_name))
        utils.untar(self.tar_name, '.')
        with open(os.path.join(
                'cloudify-script-plugin',
                wheelr.METADATA_FILE_NAME), 'r') as f:
            m = json.loads(f.read())
        self.assertEqual(m['module_version'], '1.2')
        self.assertEqual(m['module_name'], 'cloudify-script-plugin')
        self.assertEqual(m['supported_platform'], self.platform)
        self.assertTrue(len(m['wheels']) >= 8)
        self.assertEqual(
            m['archive_name'],
            'cloudify_script_plugin-1.2-{0}-none-{1}.tar.gz'.format(
                self.pyver, self.platform))
        self.assertTrue(os.path.isfile(os.path.join(
            'cloudify-script-plugin', wheelr.DEFAULT_WHEELS_PATH,
            'cloudify_script_plugin-1.2-py2-none-any.whl')))
        return m

    def test_create_plugin_package_from_pypi(self):
        result = self.runner.invoke(
            wheelr.create, ['-scloudify-script-plugin==1.2', '-v', '-f'])
        self.assertEqual(str(result), '<Result okay>')
        m = self._test()
        self.assertEqual(m['module_source'], 'cloudify-script-plugin==1.2')

    def test_create_package_from_url_with_requirements(self):
        self.tar_name = self.wheelr.set_tar_name(
            'cloudify-script-plugin', '1.2', 'linux_x86_64')
        self.platform = 'linux_x86_64'
        result = self.runner.invoke(
            wheelr.create, ['-s{0}'.format(TEST_FILE), '-v', '-f', '-r.'])
        self.assertEqual(str(result), '<Result okay>')
        m = self._test()
        self.assertEqual(m['module_source'], TEST_FILE)

    def test_create_package_from_path(self):
        source = self.wheelr.get_source(TEST_FILE)
        self.runner.invoke(
            wheelr.create, ['-s{0}'.format(source), '-v', '-f'])
        m = self._test()
        self.assertEqual(m['module_source'], source)

    def test_create_package_tar_already_exists(self):
        self.wheelr.create()
        self.assertTrue(os.path.isfile(self.tar_name))
        e = self.assertRaises(SystemExit, self.wheelr.create)
        self.assertIn('9', str(e))

    def test_create_package_tar_already_exists_force(self):
        self.wheelr.create()
        self.assertTrue(os.path.isfile(self.tar_name))
        self.wheelr.create(force=True)
        self.assertTrue(os.path.isfile(self.tar_name))

    def test_create_package_plugin_directory_already_exists(self):
        self.wheelr.create(keep_wheels=True)
        self.assertTrue(os.path.isdir('cloudify-script-plugin'))
        e = self.assertRaises(SystemExit, self.wheelr.create)
        self.assertIn('1', str(e))

    def test_create_package_plugin_directory_already_exists_force(self):
        self.wheelr.create(keep_wheels=True)
        self.assertTrue(os.path.isdir('cloudify-script-plugin'))
        self.wheelr.create(force=True)
        self.assertTrue(os.path.isfile(self.tar_name))


class TestInstall(testtools.TestCase):

    def setUp(self):
        super(TestInstall, self).setUp()
        self.runner = clicktest.CliRunner()
        self.packager = wheelr.Wheelr(
            'cloudify-script-plugin==1.2', verbose=True)
        utils.run('virtualenv test_env')
        self.tar_path = self.packager.create(force=True)

    def tearDown(self):
        super(TestInstall, self).tearDown()
        os.remove(self.tar_path)
        if os.path.isdir('test_env'):
            shutil.rmtree('test_env')

    def test_install_module_from_local_tar(self):
        result = self.runner.invoke(
            wheelr.install,
            ['-s{0}'.format(self.tar_path), '-v',
             '--virtualenv=test_env', '-u'])
        self.assertEqual(str(result), '<Result okay>')
        self.assertTrue(utils.check_installed(
            'cloudify-script-plugin', 'test_env'))


class TestValidate(testtools.TestCase):

    def setUp(self):
        super(TestValidate, self).setUp()
        self.runner = clicktest.CliRunner()
        self.packager = wheelr.Wheelr(
            'cloudify-script-plugin==1.2', verbose=True)
        self.tar_path = self.packager.create(force=True)

    def tearDown(self):
        super(TestValidate, self).tearDown()
        os.remove(self.tar_path)

    def test_validate_package(self):
        result = self.runner.invoke(
            wheelr.validate, ['-s{0}'.format(self.tar_path), '-v'])
        self.assertEqual(str(result), '<Result okay>')
