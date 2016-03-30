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


def get_appstack_resource_dir():
    return os.path.join(_get_resource_dir(), 'appstack')


def get_appstack_resource(resource_name):
    return os.path.join(get_appstack_resource_dir(), resource_name)


def get_cfclient_resource(resource_name):
    resource_dir = os.path.join(_get_resource_dir(), 'cfclient')
    return os.path.join(resource_dir, resource_name)


def _get_resource_dir():
    test_dir = os.path.realpath(os.path.dirname(__file__))
    return os.path.join(test_dir, 'resources')
