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
        self.packager = wheelr.Wheelr(
            'cloudify-script-plugin==1.2', verbose=True)
        self.tar_name = self.packager.set_tar_name(
            'cloudify-script-plugin', '1.2', 'any')
        self.pyver = utils.get_python_version()

    def tearDown(self):
        super(TestCreate, self).tearDown()
        os.remove(self.tar_name)
        if os.path.isdir(wheelr.DEFAULT_MODULE_PATH):
            shutil.rmtree(wheelr.DEFAULT_MODULE_PATH)

    def _test(self):
        self.assertTrue(os.path.isfile(self.tar_name))
        utils.untar(self.tar_name, '.')
        with open(os.path.join(
                wheelr.DEFAULT_MODULE_PATH,
                wheelr.METADATA_FILE_NAME), 'r') as f:
            m = json.loads(f.read())
        self.assertEqual(m['module_version'], '1.2')
        self.assertEqual(m['module_name'], 'cloudify-script-plugin')
        self.assertEqual(m['supported_platform'], 'any')
        self.assertTrue(len(m['wheels']) >= 8)
        self.assertEqual(
            m['archive_name'],
            'cloudify_script_plugin-1.2-{0}-none-any.tar.gz'.format(
                self.pyver))
        self.assertTrue(os.path.isfile(os.path.join(
            wheelr.DEFAULT_WHEELS_PATH,
            'cloudify_script_plugin-1.2-py2-none-any.whl')))
        return m

    def test_create_plugin_package_from_pypi(self):
        self.runner.invoke(
            wheelr.create, ['-scloudify-script-plugin==1.2', '-v', '-f'])
        m = self._test()
        self.assertEqual(m['module_source'], 'cloudify-script-plugin==1.2')

    def test_create_plugin_package_from_url(self):
        self.runner.invoke(
            wheelr.create, ['-s{0}'.format(TEST_FILE), '-v', '-f'])
        m = self._test()
        self.assertEqual(m['module_source'], TEST_FILE)

    def test_create_plugin_package_from_path(self):
        source = self.packager.get_source(TEST_FILE)
        self.runner.invoke(
            wheelr.create, ['-s{0}'.format(source), '-v', '-f'])
        m = self._test()
        self.assertEqual(m['module_source'], source)

    def test_create_package_tar_already_exists(self):
        self.packager.create()
        self.assertTrue(os.path.isfile(self.tar_name))
        e = self.assertRaises(SystemExit, self.packager.create)
        self.assertIn('9', str(e))

    def test_create_packager_tar_already_exists_force(self):
        self.packager.create()
        self.assertTrue(os.path.isfile(self.tar_name))
        self.packager.create(force=True)
        self.assertTrue(os.path.isfile(self.tar_name))

    def test_create_package_plugin_directory_already_exists(self):
        self.packager.create(keep_wheels=True)
        self.assertTrue(os.path.isdir(wheelr.DEFAULT_MODULE_PATH))
        e = self.assertRaises(SystemExit, self.packager.create)
        self.assertIn('1', str(e))

    def test_create_package_plugin_directory_already_exists_force(self):
        self.packager.create(keep_wheels=True)
        self.assertTrue(os.path.isdir(wheelr.DEFAULT_MODULE_PATH))
        self.packager.create(force=True)
        self.assertTrue(os.path.isfile(self.tar_name))
