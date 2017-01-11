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
import codecs
from setuptools import setup

if sys.version_info[:2] < (2, 6):
    sys.exit('Wagon requires Python 2.6 or higher.')

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    # intentionally *not* adding an encoding option to open
    return codecs.open(os.path.join(here, *parts), 'r').read()


setup(
    name='wagon',
    version='0.6.0',
    url='https://github.com/cloudify-cosmo/wagon',
    author='Gigaspaces',
    author_email='cosmo-admin@gigaspaces.com',
    license='Apache 2.0',
    platforms='All',
    description='Creates Python Wheel based archives with dependencies',
    long_description=read('README.rst'),
    py_modules=['wagon'],
    include_package_data=True,
    zip_safe=False,
    entry_points={'console_scripts': ['wagon = wagon:main']},
    install_requires=[
        "wheel>=0.24.0",
    ],
    extras_require={
        'dist': ['distro>=0.6.0'],
        'venv': ['virtualenv>=12.1'],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Natural Language :: English',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Microsoft',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
