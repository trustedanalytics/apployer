#
# Copyright (c) 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

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
