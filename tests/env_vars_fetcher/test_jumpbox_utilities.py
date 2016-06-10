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
import ConfigParser
from apployer.fetcher.jumpbox_utilities import ConfigurationExtractor
from mock import MagicMock


@pytest.fixture
def fetcher_config():
    return {
        "kerberos_used": True,
        "kubernetes_used": True,
        "jumpbox": {
            "hostname": "10.10.10.10",
            "hostport": 22,
            "username": "centos",
            "key_filename": "key.pem",
            "key_password": None
        },
        "cdh-manager": {
            "user": "admin",
            "password": "admin",
            "cm_port": 7180,
            "ssh_user": "user_ssh"
        },
        "paths": {
            "cf_tiny_yml": "/root/cf.yml",
            "ansible_hosts": "/etc/ansible/hosts",
            "passwords_store": "/tmp/apployer_passwords"
        },
        "envname": "trustedanalytics",
        "workers_count": 3,
        "masters_count": 3
    }


@pytest.fixture
def config_ini(section):
    config = ConfigParser.RawConfigParser()
    config.add_section(section)
    return config


def test_creating_ConfigurationExtractor_instance(fetcher_config):
    with ConfigurationExtractor(fetcher_config) as ce:
        assert ce._kerberos_used == fetcher_config['kerberos_used']
        assert ce._hostname == fetcher_config['jumpbox']['hostname']
        assert ce._hostport == fetcher_config['jumpbox']['hostport']
        assert ce._username == fetcher_config['jumpbox']['username']
        assert ce._ssh_key_filename == fetcher_config['jumpbox']['key_filename']
        assert ce._ssh_key_password == fetcher_config['jumpbox']['key_password']
        assert ce._paths == fetcher_config['paths']
        assert ce._kerberos_used == fetcher_config['kerberos_used']
        assert ce._cdh_manager_user == fetcher_config['cdh-manager']['user']
        assert ce._cdh_manager_password == fetcher_config['cdh-manager']['password']
        assert ce._cdh_manager_port == fetcher_config['cdh-manager']['cm_port']
        assert ce._cdh_manager_ssh_user == fetcher_config['cdh-manager']['ssh_user']


def test_get_deployment_configuration(fetcher_config, monkeypatch):
    get_ansible_hosts = MagicMock()
    get_data_from_cf_tiny_mock = MagicMock()
    get_data_from_cdh_manager_mock = MagicMock()
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.ConfigurationExtractor._get_ansible_hosts',
                        get_ansible_hosts)
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.ConfigurationExtractor._get_data_from_cf_tiny_yaml',
                        get_data_from_cf_tiny_mock)
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.ConfigurationExtractor._get_data_from_cdh_manager',
                        get_data_from_cdh_manager_mock)
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.ConfigurationExtractor.execute_command',
                        get_data_from_cdh_manager_mock)
    with ConfigurationExtractor(fetcher_config) as ce:
        ce.get_deployment_configuration()
        assert get_ansible_hosts.called
        assert get_data_from_cdh_manager_mock.called
        assert get_data_from_cf_tiny_mock.called


def test_get_data_from_inventory(fetcher_config, monkeypatch):
    _execute_command_mock = MagicMock()
    yaml_mock = MagicMock()
    inventory_content = {
        "properties": {
            "nats": {
                "machines": ["machine01"]
            },
            "loggregator_endpoint": {
                "shared_secret": "my_secret"
            },
            "domain": "my_domain",
            "login": {
                "smtp": {
                    "senderEmail": "myEmail",
                    "password": '"my_pass"',
                    "user": "username",
                    "port": 25,
                    "host": "hostname"
                }
            }
        },
        "jobs": [
            {
                "networks": [
                    {"static_ips": ['ip']}
                ]
            }
        ]
    }
    yaml_mock.return_value = inventory_content
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.ConfigurationExtractor.execute_command',
                        _execute_command_mock)
    monkeypatch.setattr('apployer.fetcher.jumpbox_utilities.yaml.load', yaml_mock)
    with ConfigurationExtractor(fetcher_config) as ce:
        ce._inventory = MagicMock()
        result = ce._get_data_from_cf_tiny_yaml()
        assert result["nats_ip"] == inventory_content['properties']['nats']['machines'][0]
        assert result["cf_admin_password"] == inventory_content['properties']['loggregator_endpoint']['shared_secret']
        assert result["cf_admin_client_password"] == inventory_content['properties']['loggregator_endpoint'][
            'shared_secret']
        assert result["apps_domain"] == inventory_content['properties']['domain']
        assert result["tap_console_password"] == inventory_content['properties']['loggregator_endpoint'][
            'shared_secret']
        assert result["email_address"] == inventory_content['properties']['login']['smtp']['senderEmail']
        assert result["run_domain"] == inventory_content['properties']['domain']
        assert result["smtp_pass"] == '"{}"'.format(inventory_content['properties']['login']['smtp']['password'])
        assert result["smtp_user"] == '"{}"'.format(inventory_content['properties']['login']['smtp']['user'])
        assert result["smtp_port"] == inventory_content['properties']['login']['smtp']['port']
        assert result["smtp_host"] == inventory_content['properties']['login']['smtp']['host']


def test_determine_smtp_protocol(fetcher_config):
    smtp_protocol = 'smtp'
    smtps_protocol = 'smtps'
    non_standard_port = 99999999999
    with ConfigurationExtractor(fetcher_config) as ce:
        assert ce._determine_smtp_protocol(465) == smtps_protocol
        assert ce._determine_smtp_protocol(25) == smtp_protocol
        assert ce._determine_smtp_protocol(587) == smtp_protocol
        assert ce._determine_smtp_protocol(2525) == smtp_protocol
        assert ce._determine_smtp_protocol(non_standard_port) == None


def test_find_item_by_attr_value(fetcher_config):
    source_object = {
        "testObj": [
            {
                "name": "A",
                "value": 123,
                "nextProperty": "hahaha"
            },
            {
                "name": "B",
                "value": 321,
                "nextProperty": "hihihi"
            }
        ]
    }
    with ConfigurationExtractor(fetcher_config) as ce:
        result = ce._find_item_by_attr_value(123, 'value', source_object["testObj"])
        assert result != None
        assert result['value'] == source_object['testObj'][0]['value']
        assert result['name'] == source_object['testObj'][0]['name']
        result = ce._find_item_by_attr_value('B', 'name', source_object["testObj"])
        assert result != None
        assert result['value'] == source_object['testObj'][1]['value']
        assert result['name'] == source_object['testObj'][1]['name']


def test_get_java_http_proxy(fetcher_config, monkeypatch):
    with ConfigurationExtractor(fetcher_config) as ce:
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'http_proxy', 'http://proxy.domain.com')
        assert ce._get_java_http_proxy() == '-Dhttp.proxyHost=proxy.domain.com'
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'http_proxy', 'http://proxy.domain.com:123')
        assert ce._get_java_http_proxy() == '-Dhttp.proxyHost=proxy.domain.com -Dhttp.proxyPort=123'
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'https_proxy', 'https://proxy.domain.com')
        assert ce._get_java_http_proxy() == '-Dhttps.proxyHost=proxy.domain.com'
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'https_proxy', 'https://proxy.domain.com:456')
        assert ce._get_java_http_proxy() == '-Dhttps.proxyHost=proxy.domain.com -Dhttps.proxyPort=456'
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'no_proxy', '10.10.10.10')
        assert ce._get_java_http_proxy() == '-Dhttp.nonProxyHosts=10.10.10.10|localhost|127.*|[::1]'
        ce._jumpboxes_vars = config_ini('jump-boxes:vars')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'http_proxy', 'http://proxy.example.com:8080')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'https_proxy', 'http://proxy.example.com:8080')
        ce._jumpboxes_vars.set('jump-boxes:vars', 'no_proxy', '*.apps.example.com')
        assert ce._get_java_http_proxy() == '-Dhttp.proxyHost=proxy.example.com -Dhttp.proxyPort=8080 ' \
                                            '-Dhttps.proxyHost=proxy.example.com -Dhttps.proxyPort=8080 ' \
                                            '-Dhttp.nonProxyHosts=*.apps.example.com|localhost|127.*|[::1]'
