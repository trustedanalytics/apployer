import os
from setuptools import setup, find_packages

project_name = 'apployer'

version = '0.0.1'

setup_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(setup_dir, 'requirements.txt')) as req_file:
    requirements = [lib.split('==')[0] for lib in req_file.readlines()]
with open(os.path.join(setup_dir, 'README.md')) as readme_file:
    readme = readme_file.read()


setup(
    name=project_name,
    version=version,
    packages=find_packages(exclude=['tests*']),
    install_requires=requirements,
    entry_points={'console_scripts': ['{0} = {0}.main:cli'.format(project_name)]},
    license='Apache 2.0')
