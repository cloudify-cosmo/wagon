from setuptools import setup
import os
import codecs

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    # intentionally *not* adding an encoding option to open
    return codecs.open(os.path.join(here, *parts), 'r').read()


setup(
    name='wagon',
    version='0.2.0',
    url='https://github.com/cloudify-cosmo/wagon',
    author='Gigaspaces',
    author_email='cosmo-admin@gigaspaces.com',
    license='LICENSE',
    platforms='All',
    description='Creates Python Wheel based archives.',
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
