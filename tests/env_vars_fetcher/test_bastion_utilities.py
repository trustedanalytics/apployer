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

import pytest

from apployer.fetcher.bastion_utilities import CFConfExtractor

@pytest.fixture
def fetcher_config():
    return {
        'openstack_env': True,
        'kerberos_used': True,
        'machines': {
            'cf-bastion': {
                'hostname': '10.10.10.10',
                'hostport': 22,
                'username': 'centos',
                'key_filename': 'key.pem',
                'key_password': None,
                'path_to_cf_tiny_yml': None,
                'path_to_docker_vpc_yml': None,
                'path_to_provision_sh': None
            },
            'cdh-manager-ip': ''
        }
    }


@pytest.fixture
def cf_conf_extractor(fetcher_config):
    return CFConfExtractor(fetcher_config)


def test_basic_config(cf_conf_extractor, fetcher_config):
    assert cf_conf_extractor._hostname == fetcher_config['machines']['cf-bastion']['hostname']
    assert cf_conf_extractor._hostport == fetcher_config['machines']['cf-bastion']['hostport']
    assert cf_conf_extractor._username == fetcher_config['machines']['cf-bastion']['username']
    assert cf_conf_extractor._key == fetcher_config['machines']['cf-bastion']['key_filename']


def test_set_smtp_for_ports(cf_conf_extractor):
    assert 'smtp' == cf_conf_extractor._determine_smtp_protocol(25)
    assert 'smtp' == cf_conf_extractor._determine_smtp_protocol(587)
    assert 'smtp' == cf_conf_extractor._determine_smtp_protocol(2525)


def test_set_smtps_for_port(cf_conf_extractor):
    assert 'smtps' == cf_conf_extractor._determine_smtp_protocol(465)


def test_protocol_not_set_for_unknown_port(cf_conf_extractor):
    assert None == cf_conf_extractor._determine_smtp_protocol(111111)
