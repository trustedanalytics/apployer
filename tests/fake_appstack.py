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

from apployer.appstack import (AppConfig, AppStack, BrokerConfig,
                               ServiceInstance, UserProvidedService)


def _services_to_dicts(service_list):
    return [service.__dict__ for service in service_list]


TEST_APP_X_APP_PROPERTIES = {
    'env': {
        'test_env_1': 'test_env_1_val',
        'test_env_2': 'test_env_2_val'
    },
    'disk_quota': '256M'
}

TEST_APP_X_USER_PROVIDED_SERVICES = [
    UserProvidedService('app_X_serv', {'url': 'http://app_x.example.com'})]

TEST_APP_X = AppConfig(
        'app_X',
        app_properties=TEST_APP_X_APP_PROPERTIES,
        user_provided_services=TEST_APP_X_USER_PROVIDED_SERVICES,
        register_in='app_Y')

TEST_APP_Y_BROKER_CONFIG = BrokerConfig(
    'Y_broker',
    'https://Y_broker.example.com',
    'username',
    'password',
    service_instances=[ServiceInstance('Y_1', 'shared')])

TEST_APP_Y = AppConfig('app_Y', broker_config=TEST_APP_Y_BROKER_CONFIG)

TEST_APPSTACK_USER_PROVIDED_SERVICES = [
    UserProvidedService('custom_serv', {'url': 'http://custom_serv.example.com'})]

BUILDPACK_NAME = 'example-buildpack'

TEST_APPSTACK_DICT = {
    'apps': [
        {
            'name': 'app_X',
            'app_properties': TEST_APP_X_APP_PROPERTIES,
            'user_provided_services': _services_to_dicts(TEST_APP_X_USER_PROVIDED_SERVICES),
            'register_in': 'app_Y',
        },
        {
            'name': 'app_Y',
            'broker_config': TEST_APP_Y_BROKER_CONFIG.to_dict()
        }
    ],
    'user_provided_services': _services_to_dicts(TEST_APPSTACK_USER_PROVIDED_SERVICES),
    'buildpacks': [BUILDPACK_NAME],
}

_new_appstack_dict = copy.deepcopy(TEST_APPSTACK_DICT)
_new_appstack_dict['apps'].append({'name': 'app_Z'})
TEST_APPSTACK = AppStack.from_appstack_dict(_new_appstack_dict)

TEST_APP_MANIFESTS = {
    'app_X': {
        'disk_quota': '128M',
        'instances': '1',
        'env': {
            'test_env_3': 'test_env_3_val'
        }
    },
    'app_Y': {
        'env': {
            'test_env_4': 'test_env_4_val'
        }
    }
}

TEST_APPSTACK_WITH_MANIFESTS = AppStack.from_appstack_dict({
    'apps': [
        {
            'name': 'app_X',
            'app_properties': {
                'name': 'app_X',
                'env': {
                    'test_env_1': 'test_env_1_val',
                    'test_env_2': 'test_env_2_val',
                    'test_env_3': 'test_env_3_val'
                },
                'disk_quota': '256M',
                'instances': '1',
            },
            'user_provided_services': [{
                'name': 'app_X_serv',
                'credentials': {
                    'url': 'http://app_x.example.com'
                }
            }],
            'register_in': 'app_Y',
        },
        {
            'name': 'app_Y',
            'app_properties': {
                'name': 'app_Y',
                'env': {
                    'test_env_4': 'test_env_4_val'
                }
            },
            'broker_config': {
                'name': 'Y_broker',
                'url': 'https://Y_broker.example.com',
                'auth_username': 'username',
                'auth_password': 'password',
                'service_instances': [{
                    'name': 'Y_1',
                    'plan': 'shared'
                }]
            }
        },
        {
            'name': 'app_Z',
            'app_properties': {'name': 'app_Z'}
        }
    ],
    'user_provided_services': [{
        'name': 'custom_serv',
        'credentials': {
            'url': 'http://custom_serv.example.com'
        }
    }],
    'buildpacks': [BUILDPACK_NAME],
})
