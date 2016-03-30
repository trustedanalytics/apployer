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

from collections import namedtuple

import mock
import pytest

from apployer.fetcher.cdh_utilities import CdhConfExtractor


@pytest.fixture
def fetcher_config():
    return {
        'openstack_env': True,
        'kerberos_used': True,
        'machines': {
            'cdh-launcher': {
                'hostname': '10.10.10.10',
                'hostport': 22,
                'username': 'centos',
                'key_filename': 'key.pem',
                'key_password': None
            },
            'cdh-manager': {
                'ip': '',
                'user': 'test',
                'password': 'test',
                'sshtunnel_required': True
            }
        }
    }


@pytest.fixture
def cdh_conf_extractor(fetcher_config):
    return CdhConfExtractor(fetcher_config)


def test_basic_config(cdh_conf_extractor, fetcher_config):
    assert cdh_conf_extractor._hostname == fetcher_config['machines']['cdh-launcher']['hostname']
    assert cdh_conf_extractor._hostport == fetcher_config['machines']['cdh-launcher']['hostport']
    assert cdh_conf_extractor._username == fetcher_config['machines']['cdh-launcher']['username']
    assert cdh_conf_extractor._key == fetcher_config['machines']['cdh-launcher']['key_filename']


@mock.patch('paramiko.SSHClient', create=True)
@mock.patch('paramiko.AutoAddPolicy', create=True)
def test_create_and_close_SSHConnection(mock_policy, ssh_client, cdh_conf_extractor):
    SSHClientMock = namedtuple('SSHClient', 'connect set_missing_host_key_policy close')
    ssh_client_mock = SSHClientMock(
        connect=mock.Mock(),
        set_missing_host_key_policy=mock.Mock(),
        close=mock.Mock()
    )
    ssh_client.return_value = ssh_client_mock
    mock_policy.return_value = mock.Mock()

    cdh_conf_extractor.create_ssh_connection(
        cdh_conf_extractor._hostname,
        cdh_conf_extractor._username,
        cdh_conf_extractor._key,
        cdh_conf_extractor._key_password)
    cdh_conf_extractor.close_ssh_connection()

    assert ssh_client_mock.set_missing_host_key_policy.call_count == 1
    assert ssh_client_mock.connect.call_count == 1
    assert ssh_client_mock.close.call_count == 1
    assert mock_policy.call_count == 1
    ssh_client_mock.connect.assert_called_with(
        cdh_conf_extractor._hostname,
        key_filename=cdh_conf_extractor._key,
        password=cdh_conf_extractor._key_password,
        username=cdh_conf_extractor._username)
