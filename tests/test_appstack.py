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

import copy

import pytest

from apployer.appstack import AppConfig, AppStack, DataContainer, MalformedAppStackError
from .fake_appstack import (TEST_APP_X, TEST_APP_Y, TEST_APPSTACK_DICT,
                            TEST_APPSTACK_USER_PROVIDED_SERVICES, TEST_APPSTACK, TEST_APP_MANIFESTS,
                            TEST_APPSTACK_WITH_MANIFESTS, BUILDPACK_NAME, TEST_SECURITY_GROUP)


def test_data_container_eq():
    a, b = DataContainer(), DataContainer()
    assert a == b
    a.something = 'qwerty'
    assert a != b
    assert not a.__eq__('something-else')


@pytest.mark.parametrize('appstack_properties, manifest, merged_app_properties', [
    (
        {
            'env': {
                'test_env_1': 'test_env_1_val',
                'test_env_2': 'test_env_2_val'
            },
            'disk_quota': '256M'
        },
        {
            'disk_quota': '128M',
            'instances': '1',
            'env': {
                'test_env_2': 'test_env_2_val_alt',
                'test_env_3': 'test_env_3_val'
            }
        },
        {
            'env': {
                'test_env_1': 'test_env_1_val',
                'test_env_2': 'test_env_2_val',
                'test_env_3': 'test_env_3_val'
            },
            'disk_quota': '256M',
            'instances': '1',
        }
    ),
    (
        {
            'disk_quota': '512M'
        },
        {
            'env': {
                'test_env': 'test_env_val'
            }
        },
        {
            'env': {
                'test_env': 'test_env_val',
            },
            'disk_quota': '512M',
        }
    ),
    (
        {'services': ['a', 'b']},
        {'services': ['c']},
        {'services': list(set(['a', 'b', 'c']))}
    ),
    (
        {},
        {'disk_quota': '512M'},
        {'disk_quota': '512M'}
    ),
])
def test_merge_app_config_and_manifest(appstack_properties, manifest, merged_app_properties):
    app_name = 'test_app'
    merged_app_properties['name'] = app_name
    app_config = AppConfig(app_name, app_properties=appstack_properties)
    proper_merged_app_cfg = AppConfig(app_name, app_properties=merged_app_properties)

    merged_app_cfg = app_config.merge_manifest(manifest)

    assert merged_app_cfg == proper_merged_app_cfg


@pytest.mark.parametrize('config_kwargs', [
    {'name': ''},
    {'name': 'bla', 'order': 'not-a-number'}
])
def test_create_app_malformed(config_kwargs):
    with pytest.raises(MalformedAppStackError):
        AppConfig(**config_kwargs)


def test_parse_appstack():
    appstack = AppStack.from_appstack_dict(TEST_APPSTACK_DICT)
    assert appstack.apps == [TEST_APP_X, TEST_APP_Y]
    assert appstack.user_provided_services == TEST_APPSTACK_USER_PROVIDED_SERVICES
    assert appstack.buildpacks == [BUILDPACK_NAME]
    assert appstack.security_groups == [TEST_SECURITY_GROUP]


def test_parse_invalid_appstack():
    appstack_dict = copy.deepcopy(TEST_APPSTACK_DICT)
    del appstack_dict['apps'][0]['name']
    with pytest.raises(MalformedAppStackError):
        AppStack.from_appstack_dict(appstack_dict)


def test_parse_appstack_nonexistent_registrator():
    with pytest.raises(MalformedAppStackError):
        AppStack(apps=[AppConfig('bla', register_in='bla2')])


def test_merge_manifests():
    expanded_appstack = TEST_APPSTACK.merge_manifests(TEST_APP_MANIFESTS)
    assert TEST_APPSTACK_WITH_MANIFESTS == expanded_appstack
