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
import codecs
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    # intentionally *not* adding an encoding option to open
    return codecs.open(os.path.join(here, *parts), 'r').read()


setup(
    name='wagon',
    version='0.3.1',
    url='https://github.com/cloudify-cosmo/wagon',
    author='Gigaspaces',
    author_email='cosmo-admin@gigaspaces.com',
    license='LICENSE',
    platforms='All',
    description='Creates Python Wheel based archives with dependencies.',
    long_description=read('README.rst'),
    packages=['wagon'],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'wagon = wagon.wagon:main',
        ]
    },
    install_requires=[
        "wheel>=0.24.0",
        "virtualenv>=12.1",
        "click==4.0",
    ]
)
