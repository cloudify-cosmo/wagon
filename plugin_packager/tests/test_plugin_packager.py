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

__author__ = 'nir0s'

import plugin_packager.packager as pp
import plugin_packager.utils as utils
# import plugin_packager.codes as codes
# from plugin_packager.logger import init
# from requests import ConnectionError

import click.testing as clicktest
# import imp
# from contextlib import closing
# from testfixtures import LogCapture
# import logging
# import tarfile
import testtools
import os
import json
import shutil


TEST_RESOURCES_DIR = 'agent_packager/tests/resources/'
CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'config_file.yaml')
BAD_CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'bad_config_file.yaml')
EMPTY_CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'empty_config_file.yaml')
BASE_DIR = 'cloudify'
TEST_VENV = os.path.join(BASE_DIR, 'env')
TEST_MODULE = 'xmltodict'
TEST_FILE = 'https://github.com/cloudify-cosmo/cloudify-agent-packager/archive/master.tar.gz'  # NOQA
MANAGER = 'https://github.com/cloudify-cosmo/cloudify-manager/archive/master.tar.gz'  # NOQA
MOCK_MODULE = os.path.join(TEST_RESOURCES_DIR, 'mock-module')
MOCK_MODULE_NO_INCLUDES_FILE = os.path.join(
    TEST_RESOURCES_DIR, 'mock-module-no-includes')


# class TestUtils(testtools.TestCase):

#     def test_set_global_verbosity_level(self):
#         lgr = init(base_level=logging.INFO)

#         with LogCapture() as l:
#             ap.set_global_verbosity_level(is_verbose_output=False)
#             lgr.debug('TEST_LOGGER_OUTPUT')
#             l.check()
#             lgr.info('TEST_LOGGER_OUTPUT')
#             l.check(('user', 'INFO', 'TEST_LOGGER_OUTPUT'))

#             ap.set_global_verbosity_level(is_verbose_output=True)
#             lgr.debug('TEST_LOGGER_OUTPUT')
#             l.check(
#                 ('user', 'INFO', 'TEST_LOGGER_OUTPUT'),
#                 ('user', 'DEBUG', 'TEST_LOGGER_OUTPUT'))

#     def test_run(self):
#         p = utils.run('uname')
#         self.assertEqual(0, p.returncode)

#     def test_run_bad_command(self):
#         p = utils.run('suname')
#         self.assertEqual(127, p.returncode)

#     def test_download_file(self):
#         utils.download_file(TEST_FILE, 'file')
#         if not os.path.isfile('file'):
#             raise Exception('file not downloaded')
#         os.remove('file')

#     def test_download_file_missing(self):
#         e = self.assertRaises(
#             SystemExit, utils.download_file,
#             'http://www.google.com/x.tar.gz', 'file')
#         self.assertEqual(
#             codes.errors['could_not_download_file'], e.message)

#     def test_download_bad_url(self):
#         e = self.assertRaises(
#             Exception, utils.download_file, 'something', 'file')
#         self.assertIn('Invalid URL', e.message)

#     def test_download_connection_failed(self):
#         e = self.assertRaises(
#             ConnectionError, utils.download_file, 'http://something', 'file')
#         self.assertIn('Connection aborted', str(e))

#     def test_download_missing_path(self):
#         e = self.assertRaises(
#             IOError, utils.download_file, TEST_FILE, 'x/file')
#         self.assertIn('No such file or directory', e)

#     def test_download_no_permissions(self):
#       e = self.assertRaises(IOError, utils.download_file, TEST_FILE, '/file')
#         self.assertIn('Permission denied', e)

#     def test_tar(self):
#         os.makedirs('dir')
#         with open('dir/content.file', 'w') as f:
#             f.write('CONTENT')
#         utils.tar('dir', 'tar.file')
#         shutil.rmtree('dir')
#         self.assertTrue(tarfile.is_tarfile('tar.file'))
#         with closing(tarfile.open('tar.file', 'r:gz')) as tar:
#             members = tar.getnames()
#             self.assertIn('dir/content.file', members)
#         os.remove('tar.file')

#     def test_tar_no_permissions(self):
#         e = self.assertRaises(SystemExit, utils.tar, TEST_VENV, '/file')
#         self.assertEqual(e.message, codes.errors['failed_to_create_tar'])

#     def test_tar_missing_source(self):
#         e = self.assertRaises(SystemExit, utils.tar, 'missing', 'file')
#         self.assertEqual(e.message, codes.errors['failed_to_create_tar'])
#         os.remove('file')


class TestCreate(testtools.TestCase):

    def test_create_plugin_package_from_pypi(self):
        runner = clicktest.CliRunner()
        packager = pp.PluginPackager(
            'cloudify-script-plugin==1.2', verbose=True)
        tar_name = packager.set_tar_name(
            'cloudify-script-plugin', '1.2', 'any')
        try:
            runner.invoke(
                pp.create, ['-scloudify-script-plugin==1.2', '-v', '-f'])
            packager = pp.PluginPackager(
                'cloudify-script-plugin==1.2', verbose=True)
            tar_name = packager.set_tar_name(
                'cloudify-script-plugin', '1.2', 'any')
            self.assertTrue(os.path.isfile(tar_name))
            utils.untar(tar_name, '.')
            # mock_metadata = {
            #     "archive_name":
            #     "cloudify_script_plugin-1.2-py27-none-any.tar.gz",
            #     "platform": "any",
            #     "plugin_name": "cloudify-script-plugin",
            #     "plugin_source": "cloudify-script-plugin==1.2",
            #     "plugin_version": "1.2",
            #     "wheels": [
            #         "proxy_tools-0.1.0-py2-none-any.whl",
            #         "bottle-0.12.7-py2-none-any.whl",
            #         "networkx-1.8.1-py2-none-any.whl",
            #         "pika-0.9.13-py2-none-any.whl",
            #         "cloudify_plugins_common-3.2.1-py2-none-any.whl",
            #         "requests-2.7.0-py2.py3-none-any.whl",
            #         "cloudify_rest_client-3.2.1-py2-none-any.whl",
            #         "cloudify_script_plugin-1.2-py2-none-any.whl"
            #     ]
            # }
            with open(os.path.join('plugin', 'plugin.json'), 'r') as f:
                m = json.loads(f.read())
            # self.assertDictEqual(mock_metadata, metadata)
            self.assertEqual(m['plugin_source'], 'cloudify-script-plugin==1.2')
            self.assertEqual(m['plugin_version'], '1.2')
            self.assertEqual(m['plugin_name'], 'cloudify-script-plugin')
            self.assertEqual(m['platform'], 'any')
            pyver = utils.get_python_version()
            if pyver == 'py27':
                self.assertEqual(len(m['wheels']), 8)
            elif pyver == 'py26':
                self.assertEqual(len(m['wheels']), 9)
            self.assertEqual(
                m['archive_name'],
                'cloudify_script_plugin-1.2-{0}-none-any.tar.gz'.format(pyver))
            self.assertTrue(os.path.isfile(os.path.join(
                'plugin', 'wheels',
                'cloudify_script_plugin-1.2-py2-none-any.whl')))
        finally:
            os.remove(tar_name)
            if os.path.isdir('plugin'):
                shutil.rmtree('plugin')

    def test_create_package_tar_already_exists(self):
        packager = pp.PluginPackager(
            'cloudify-script-plugin==1.2', verbose=True)
        tar_name = packager.set_tar_name(
            'cloudify-script-plugin', '1.2', 'any')
        try:
            packager.create()
            self.assertTrue(os.path.isfile(tar_name))
            ex = self.assertRaises(SystemExit, packager.create)
            self.assertIn('9', str(ex))
        finally:
            os.remove(tar_name)
            if os.path.isdir('plugin'):
                shutil.rmtree('plugin')
