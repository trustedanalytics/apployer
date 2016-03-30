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

import itertools
import os

import pytest
import yaml

from apployer.appstack import AppConfig, AppStack, UserProvidedService, BrokerConfig
from apployer.appstack_expand import expand_appstack, _sort_appstack
from .utils import artifacts_location, get_appstack_resource_dir

app_a_upsi_name = 'app_a_upsi'
app_a = AppConfig(
        name='app_a',
        user_provided_services=[UserProvidedService(app_a_upsi_name, {})])
app_b_upsi_name = 'app_b_upsi'
app_b = AppConfig(
        name='app_b',
        app_properties={'services': [app_a_upsi_name]},
        user_provided_services=[UserProvidedService(app_b_upsi_name, {})])
app_c = AppConfig(
        name='app_c',
        app_properties={'services': [app_a_upsi_name, app_b_upsi_name]})

app_d_instance_name = 'app_d_broker_instance'
broker_d = BrokerConfig('name', 'url', 'username', 'password',
                        service_instances=[UserProvidedService(app_d_instance_name, {})])
app_d = AppConfig(
        name='app_d',
        app_properties={'services': [app_a_upsi_name]},
        broker_config=broker_d)
app_e = AppConfig(
        name='app_e',
        app_properties={'services': [app_d_instance_name]})
app_f = AppConfig(
        name='app_f',
        order=0,
        app_properties={'services': [app_a_upsi_name]})
app_g = AppConfig(name='app_g', order=1)


@pytest.mark.parametrize('sorted_apps', [
    [app_a, app_b, app_c],
    [app_a, app_d, app_e],
    [app_f, app_a, app_b],
    [app_f, app_g, app_a, app_b]
])
def test_sort_appstack(sorted_apps):
    for apps_tuple in itertools.permutations(sorted_apps):
        unsorted_appstack = AppStack(
                apps=list(apps_tuple),
                user_provided_services=[],
                brokers=[])
        sorted_appstack = _sort_appstack(unsorted_appstack)
        assert sorted_appstack.apps == sorted_apps


def test_sort_unlinked_apps():
    app_g = AppConfig(name='app_g')
    app_h = AppConfig(name='app_h')
    apps = {app_a, app_b, app_h, app_g}
    unsorted_appstack = AppStack(list(apps), [], [])

    sorted_appstack = _sort_appstack(unsorted_appstack)

    assert apps == set(sorted_appstack.apps)


def test_appstack_expander(tmpdir, artifacts_location):
    appstack_file_path = os.path.join(get_appstack_resource_dir(), 'appstack.yml')
    expanded_appstack_path = tmpdir.join('expanded_appstack.yml').strpath
    app_dependencies = {
        'A': 'BCDEFGH',
        'B': 'EH',
        'C': 'FGH',
        'D': 'FGH',
        'E': 'H',
        'F': 'GH',
        'G': 'H',
        'H': ''
    }

    expand_appstack(appstack_file_path, artifacts_location, expanded_appstack_path)

    with open(expanded_appstack_path, 'r') as f:
        expanded_appstack_dict = yaml.load(f)
        expanded_appstack = AppStack.from_appstack_dict(expanded_appstack_dict)
        app_indices = {app.name: index for index, app in enumerate(expanded_appstack.apps)}
        for app_name in app_indices:
            for required_app in app_dependencies[app_name]:
                assert app_indices[app_name] > app_indices[required_app]

# TODO test for exceptions
# TODO create broker object. some fields will be required
