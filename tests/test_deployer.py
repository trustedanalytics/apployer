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

import json
import os

import mock
from mock import MagicMock
import pytest
import yaml

from apployer import deployer
from apployer.appstack import (AppStack, AppConfig, UserProvidedService, BrokerConfig, PushOptions,
                               ServiceInstance)
from apployer.cf_cli import CommandFailedError

from .fake_cli_outputs import GET_ENV_SUCCESS
from .utils import get_appstack_resource
from .test_cf_api import SERVICE_BINDING


@pytest.fixture
def apployer_output(tmpdir):
    return tmpdir.join('apployer_output').strpath


@pytest.fixture(scope='session')
def filled_appstack_dict():
    with open(get_appstack_resource('expanded_appstack.yml')) as filled_appstack_file:
        return yaml.load(filled_appstack_file)


@pytest.fixture
def filled_appstack(filled_appstack_dict):
    return AppStack.from_appstack_dict(filled_appstack_dict)


@pytest.fixture
def app_deployer(filled_appstack, apployer_output):
    app = next(app for app in filled_appstack.apps if app.name == 'B')
    app.push_options = PushOptions('--some --options', 'some evil --command')
    return deployer.AppDeployer(app, apployer_output)


@pytest.fixture
def mock_cf_cli(monkeypatch):
    mock_cf = MagicMock()
    monkeypatch.setattr('apployer.deployer.cf_cli', mock_cf)
    return mock_cf


def test_get_app_version(app_deployer, mock_cf_cli):
    app_version = '6.6.6'
    mock_cf_cli.env.return_value = GET_ENV_SUCCESS

    assert app_deployer._get_app_version() == app_version
    mock_cf_cli.env.assert_called_once_with(app_deployer.app.name)


def test_prepare_app(artifacts_location, app_deployer):
    prepared_app_path = app_deployer.prepare(artifacts_location)

    app_manifest_path = os.path.join(prepared_app_path, 'manifest.yml')
    filled_app_manifest_path = os.path.join(prepared_app_path, deployer.AppDeployer.FILLED_MANIFEST)
    assert os.path.exists(app_manifest_path)
    with open(filled_app_manifest_path) as filled_manifest_file:
        manifest_dict = yaml.load(filled_manifest_file)
    assert manifest_dict == {'applications': [app_deployer.app.app_properties]}


@pytest.mark.parametrize('live_version, appstack_version, strategy, push_needed', [
    ('0.0.1', '0.0.2', deployer.UPGRADE_STRATEGY, True),
    ('0.0.3', '0.0.2', deployer.UPGRADE_STRATEGY, False),
    ('0.0.1', '0.0.2', deployer.PUSH_ALL_STRATEGY, True),
    ('0.0.3', '0.0.2', deployer.PUSH_ALL_STRATEGY, True),
])
def test_check_push_needed(live_version, appstack_version, strategy, push_needed):
    app = AppConfig('bla', app_properties={'env': {'VERSION': appstack_version}})
    app_deployer = deployer.AppDeployer(app, 'some-fake-path')
    app_deployer._get_app_version = lambda: live_version

    assert app_deployer._check_push_needed(strategy) == push_needed


def test_check_push_needed_get_version_fail():
    app_deployer = deployer.AppDeployer(AppConfig('bla'), 'some-fake-path')
    app_deployer._get_app_version = MagicMock(side_effect=CommandFailedError)

    assert app_deployer._check_push_needed(deployer.UPGRADE_STRATEGY)


def test_push_app(app_deployer, monkeypatch, mock_cf_cli):
    # arrange
    artifacts_location = '/bla/release/apps'
    push_strategy = 'some-fake-strategy'
    post_commands = 'blabla bla'
    prepared_app_path = '/bla/release/apps/tested_app'
    app_manifest_location = os.path.join(prepared_app_path, deployer.AppDeployer.FILLED_MANIFEST)

    mock_check_call, mock_prepare = [MagicMock() for _ in range(2)]
    app_deployer._check_push_needed = lambda _: True
    app_deployer.prepare = mock_prepare
    mock_prepare.return_value = prepared_app_path
    monkeypatch.setattr('apployer.deployer.subprocess.check_call', mock_check_call)

    # act
    app_deployer._push_app(artifacts_location, push_strategy)

    # assert
    mock_prepare.assert_called_with(artifacts_location)
    mock_cf_cli.push.assert_called_with(prepared_app_path, app_manifest_location,
                                 app_deployer.app.push_options.params)
    mock_check_call.called_with(post_commands.split())


def test_push_app_not_needed(app_deployer, monkeypatch):
    mock_check_call = MagicMock()
    app_deployer._check_push_needed = lambda _: False
    monkeypatch.setattr('apployer.deployer.subprocess.check_call', mock_check_call)

    app_deployer._push_app('/bla/release/apps', 'some-fake-strategy')


@pytest.fixture
def broker():
    return BrokerConfig('some-name', 'https://some-name.example.com', 'username', 'password',
                        service_instances=[ServiceInstance('a', 'b'), ServiceInstance('c', 'd')])


@pytest.fixture
def mock_setup_service(monkeypatch):
    setup_service = MagicMock()
    monkeypatch.setattr('apployer.deployer.setup_service_instance', setup_service)
    return setup_service


@pytest.fixture
def mock_enable_broker_access(monkeypatch):
    enable_access = MagicMock()
    monkeypatch.setattr('apployer.deployer._enable_broker_access', enable_access)
    return enable_access


def test_setup_broker_new(broker, mock_enable_broker_access,
                          mock_setup_service, mock_cf_cli):
    mock_cf_cli.update_service_broker.side_effect = CommandFailedError

    deployer.setup_broker(broker)

    mock_cf_cli.create_service_broker.assert_called_with(broker.name, broker.auth_username,
                                                         broker.auth_password, broker.url)
    mock_enable_broker_access.assert_called_with(broker)
    assert mock.call(broker, broker.service_instances[0]) in mock_setup_service.call_args_list
    assert mock.call(broker, broker.service_instances[1]) in mock_setup_service.call_args_list


def test_setup_broker_update(mock_cf_cli, mock_setup_service, mock_enable_broker_access):
    broker = BrokerConfig('some-name', 'https://some-name.example.com', 'username', 'password')

    deployer.setup_broker(broker)

    mock_cf_cli.update_service_broker.assert_called_with(broker.name, broker.auth_username,
                                                         broker.auth_password, broker.url)
    assert mock_enable_broker_access.call_args_list
    assert not mock_setup_service.call_args_list


def test_enable_broker_access(broker, mock_cf_cli):
    service_instances = [ServiceInstance('a', 'b', 'c'), ServiceInstance('d', 'e'),
                         ServiceInstance('f', 'g'), ServiceInstance('h', 'i', 'j')]
    broker.service_instances = service_instances

    deployer._enable_broker_access(broker)

    calls = [mock.call('c'), mock.call('j'), mock.call(broker.name)]
    for call in calls:
        assert call in mock_cf_cli.enable_service_access.call_args_list
    assert len(mock_cf_cli.enable_service_access.call_args_list) == 3


def test_enable_broker_access_no_broker_service(broker, mock_cf_cli):
    mock_cf_cli.enable_service_access.side_effect = CommandFailedError
    deployer._enable_broker_access(broker)
    mock_cf_cli.enable_service_access.assert_called_once_with(broker.name)


@pytest.fixture
def upsi_deployer():
    upsi = UserProvidedService('some-name', {'a': 'b'})
    return deployer.UpsiDeployer(upsi)


def test_create_user_provided_service(mock_cf_cli, upsi_deployer):
    mock_cf_cli.get_service_guid.side_effect = CommandFailedError

    upsi_deployer.deploy()

    mock_cf_cli.get_service_guid.assert_called_with(upsi_deployer.service.name)
    mock_cf_cli.create_user_provided_service.assert_called_with(
        upsi_deployer.service.name, json.dumps(upsi_deployer.service.credentials))


def test_update_user_provided_service_needed(mock_cf_cli, upsi_deployer):
    service_guid = 'some-fake-guid'
    app_guids = ['some', 'fake', 'guids']
    mock_cf_cli.get_service_guid.return_value = service_guid
    mock_update = MagicMock(return_value=app_guids)
    upsi_deployer._update = mock_update

    assert upsi_deployer.deploy() == app_guids

    mock_update.assert_called_with(service_guid)


@pytest.fixture
def mock_cf_api(monkeypatch):
    cf_api = MagicMock()
    monkeypatch.setattr('apployer.deployer.cf_api', cf_api)
    return cf_api


def test_update_upsi(mock_cf_api, mock_cf_cli, upsi_deployer):
    service_guid = 'some-fake-guid'
    service_bindings = [SERVICE_BINDING]
    mock_cf_api.get_upsi_bindings.return_value = service_bindings
    mock_cf_api.get_upsi_credentials.return_value = {'something': 123}
    upsi_deployer._rebind_services = MagicMock()

    assert upsi_deployer._update(service_guid) == [SERVICE_BINDING['entity']['app_guid']]

    mock_cf_api.get_upsi_credentials.assert_called_with(service_guid)
    mock_cf_api.get_upsi_bindings.assert_called_with(service_guid)
    mock_cf_cli.update_user_provided_service(
        upsi_deployer.service.name, json.dumps(upsi_deployer.service.credentials))
    upsi_deployer._rebind_services.assert_called_with(service_bindings)


def test_update_upsi_not_needed(mock_cf_api, mock_cf_cli, upsi_deployer):
    service_guid = 'some-fake-guid'
    mock_cf_api.get_upsi_credentials.return_value = upsi_deployer.service.credentials

    assert upsi_deployer._update(service_guid) == []

    mock_cf_api.get_upsi_credentials.assert_called_with(service_guid)
    assert not mock_cf_api.get_upsi_bindings.call_args_list
    assert not mock_cf_cli.update_user_provided_service.call_args_list


def test_rebind_services(mock_cf_api, upsi_deployer):
    upsi_deployer._rebind_services([SERVICE_BINDING])

    mock_cf_api.delete_service_binding.assert_called_with(SERVICE_BINDING)
    mock_cf_api.create_service_binding.assert_called_with(
        SERVICE_BINDING['entity']['service_instance_guid'],
        SERVICE_BINDING['entity']['app_guid'])


def test_setup_service_instance(broker, mock_cf_cli):
    mock_cf_cli.service.side_effect = CommandFailedError
    service = broker.service_instances[0]

    deployer.setup_service_instance(broker, service)

    mock_cf_cli.create_service.assert_called_with(broker.name, service.plan, service.name)


def test_setup_service_instance_not_needed(broker, mock_cf_cli):
    service = broker.service_instances[0]

    deployer.setup_service_instance(broker, service)

    mock_cf_cli.service.assert_called_with(service.name)
    assert not mock_cf_cli.create_service.call_args_list


def test_create_buildpack(monkeypatch, mock_cf_cli):
    mock_get_file_path = MagicMock()
    buildpack_name = 'some-buildpack'
    tools_dir = '/bla/tools/'
    buildpack_path = tools_dir + 'some-buildpack-v1.2.3'
    monkeypatch.setattr('apployer.app_file.get_file_path', mock_get_file_path)
    monkeypatch.setattr('apployer.deployer._check_buildpack_needed',
                        MagicMock(side_effect=StopIteration))
    mock_get_file_path.return_value = buildpack_path

    deployer.setup_buildpack(buildpack_name, tools_dir)

    mock_get_file_path.assert_called_with(buildpack_name, tools_dir)
    mock_cf_cli.create_buildpack.assert_called_with(buildpack_name, buildpack_path)


def test_update_buildpack(monkeypatch, mock_cf_cli):
    buildpack_name = 'some-buildpack'
    tools_dir = '/bla/tools/'
    buildpack_path = tools_dir + 'some-buildpack-v1.2.3'
    monkeypatch.setattr('apployer.app_file.get_file_path', lambda _, __: buildpack_path)
    monkeypatch.setattr('apployer.deployer._check_buildpack_needed', MagicMock(return_value=True))

    deployer.setup_buildpack(buildpack_name, tools_dir)

    mock_cf_cli.update_buildpack.assert_called_with(buildpack_name, buildpack_path)
    assert not mock_cf_cli.create_buildpack.call_args_list


def test_run_ignoring_errors():
    def some_func(arg):
        return arg + 1

    def some_raising_func():
        raise Exception('blablabla')

    assert deployer.run_ignoring_errors(False, some_func, 1) == 2
    assert deployer.run_ignoring_errors(True, some_func, 1) == 2
    deployer.run_ignoring_errors(True, some_raising_func)
    with pytest.raises(Exception):
        deployer.run_ignoring_errors(False, some_raising_func)


# TODO test register in application broker

# TODO this should be a more integration test. It should work on mocked out CF or mocked CF CLI
# @pytest.mark.xfail
# def test_deploy_appstack_with_artifacts(artifacts_location, cf_info, monkeypatch):
#     filled_appstack = ''
#
#     deployer.deploy_appstack(cf_info, filled_appstack, artifacts_location)
