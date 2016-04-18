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
                               SecurityGroup, ServiceInstance)
from apployer.cf_cli import CommandFailedError, CfInfo, BuildpackDescription

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
    """Returns a deployer for app "B" from expanded appstack in test resources."""
    app = next(app for app in filled_appstack.apps if app.name == 'B')
    app.push_options = PushOptions('--some --options', 'some evil --command')
    return deployer.AppDeployer(app, apployer_output)


@pytest.fixture
def mock_cf_cli(monkeypatch):
    mock_cf = MagicMock()
    monkeypatch.setattr('apployer.deployer.cf_cli', mock_cf)
    return mock_cf


@pytest.fixture
def mock_upsi_deployer(monkeypatch):
    """Returns a mock of `UpsiDeployer` class.
    If instantiated it will return another mock that will act as a created object."""
    mock_init = MagicMock(return_value=MagicMock())
    monkeypatch.setattr('apployer.deployer.UpsiDeployer', mock_init)
    return mock_init


@pytest.fixture
def mock_setup_broker(monkeypatch):
    mock_setup = MagicMock()
    monkeypatch.setattr('apployer.deployer.setup_broker', mock_setup)
    return mock_setup


def test_app_deploy(app_deployer, mock_upsi_deployer, mock_setup_broker):
    artifacts_location = 'some/fake/location'
    is_dry_run = True
    is_push_needed = True
    broker = BrokerConfig('name', 'url', 'user', 'pass')
    app_deployer.app.broker_config = broker
    apps_to_restart = ['some-fake-guid-1', 'some-fake-guid-2']
    mock_push_app = MagicMock()
    app_deployer._push_app = mock_push_app
    mock_execute_post_command = MagicMock()
    app_deployer._execute_post_command = mock_execute_post_command

    mock_upsi_deployer.return_value.deploy.return_value = apps_to_restart

    assert app_deployer.deploy(artifacts_location, is_dry_run) == apps_to_restart

    mock_push_app.assert_called_with(artifacts_location, is_push_needed)
    mock_upsi_deployer.assert_called_with(app_deployer.app.user_provided_services[0])
    mock_setup_broker.assert_called_with(broker)
    mock_execute_post_command.assert_called_with(is_dry_run)


def test_execute_post_command(app_deployer, mock_check_call):
    is_dry_run = False
    app_deployer._execute_post_command(is_dry_run)
    mock_check_call.assert_called_with('some evil --command', shell=True)


def test_get_app_version(app_deployer, mock_cf_cli):
    app_version = '6.6.6'
    mock_cf_cli.env.return_value = GET_ENV_SUCCESS

    assert app_deployer._get_app_version() == app_version
    mock_cf_cli.env.assert_called_once_with(app_deployer.app.name)


def test_get_app_version_fail(app_deployer, mock_cf_cli):
    mock_cf_cli.env.return_value = 'some fake output \n without any version'

    with pytest.raises(deployer.AppVersionNotFoundError):
        app_deployer._get_app_version()


def test_prepare_app(artifacts_location, app_deployer):
    prepared_app_path = app_deployer.prepare(artifacts_location)

    app_manifest_path = os.path.join(prepared_app_path, 'manifest.yml')
    filled_app_manifest_path = os.path.join(prepared_app_path,
                                            deployer.AppDeployer.FILLED_MANIFEST)
    assert os.path.exists(app_manifest_path)
    with open(filled_app_manifest_path) as filled_manifest_file:
        manifest_dict = yaml.load(filled_manifest_file)
    assert manifest_dict == {'applications': [app_deployer.app.app_properties]}


def test_prepare_app_no_artifact(app_deployer):
    with pytest.raises(IOError):
        app_deployer.prepare('/some/fake/location')


@pytest.mark.parametrize('live_version, appstack_version, strategy, push_needed', [
    ('0.0.1', '0.0.2', deployer.UPGRADE_STRATEGY, True),
    ('0.0.3', '0.0.2', deployer.UPGRADE_STRATEGY, False),
    ('0.0.1', '0.0.2', deployer.PUSH_ALL_STRATEGY, True),
    ('0.0.3', '0.0.2', deployer.PUSH_ALL_STRATEGY, True),
])
def test_check_app_push_needed(live_version, appstack_version, strategy, push_needed):
    app = AppConfig('bla', app_properties={'env': {'VERSION': appstack_version}})
    app_deployer = deployer.AppDeployer(app, 'some-fake-path')
    app_deployer._get_app_version = lambda: live_version

    assert app_deployer._check_push_needed(strategy) == push_needed


def test_check_app_push_needed_get_version_fail():
    app_deployer = deployer.AppDeployer(AppConfig('bla'), 'some-fake-path')
    app_deployer._get_app_version = MagicMock(side_effect=CommandFailedError)

    assert app_deployer._check_push_needed(deployer.UPGRADE_STRATEGY)


@pytest.fixture
def mock_check_call(monkeypatch):
    mock_check = MagicMock()
    monkeypatch.setattr('apployer.deployer.subprocess.check_call', mock_check)
    return mock_check


def test_push_app(app_deployer, mock_check_call, mock_cf_cli):
    # arrange
    artifacts_location = '/bla/release/apps'
    push_strategy = 'some-fake-strategy'
    post_commands = 'blabla bla'
    prepared_app_path = '/bla/release/apps/tested_app'
    app_manifest_location = os.path.join(prepared_app_path, deployer.AppDeployer.FILLED_MANIFEST)

    mock_prepare = MagicMock()
    app_deployer._check_push_needed = lambda _: True
    app_deployer.prepare = mock_prepare
    mock_prepare.return_value = prepared_app_path

    # act
    app_deployer._push_app(artifacts_location, push_strategy)

    # assert
    mock_prepare.assert_called_with(artifacts_location)
    mock_cf_cli.push.assert_called_with(prepared_app_path, app_manifest_location,
                                 app_deployer.app.push_options.params)
    mock_check_call.called_with(post_commands.split())


def test_push_app_not_needed(app_deployer, mock_cf_cli, monkeypatch):
    is_push_needed = False
    app_deployer._push_app('/bla/release/apps', is_push_needed)
    mock_cf_cli.push.assert_not_called()


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
    mock_cf_cli.service_brokers.return_value = {'no', 'broker', 'that', 'we', 'want'}

    deployer.setup_broker(broker)

    mock_cf_cli.create_service_broker.assert_called_with(broker.name, broker.auth_username,
                                                         broker.auth_password, broker.url)
    mock_enable_broker_access.assert_called_with(broker)
    assert mock_cf_cli.service_brokers.call_args_list
    assert mock.call(broker, broker.service_instances[0]) in mock_setup_service.call_args_list
    assert mock.call(broker, broker.service_instances[1]) in mock_setup_service.call_args_list


def test_setup_broker_update(mock_cf_cli, mock_setup_service, mock_enable_broker_access):
    broker = BrokerConfig('some-name', 'https://some-name.example.com', 'username', 'password')
    mock_cf_cli.service_brokers.return_value = {broker.name}

    deployer.setup_broker(broker)

    mock_cf_cli.update_service_broker.assert_called_with(broker.name, broker.auth_username,
                                                         broker.auth_password, broker.url)
    assert mock_enable_broker_access.call_args_list
    assert not mock_setup_service.call_args_list


def test_enable_broker_access(broker, mock_cf_cli):
    service_instances = [ServiceInstance('a', 'b', 'c'), ServiceInstance('d', 'e'),
                         ServiceInstance('f', 'g'), ServiceInstance('h', 'i', 'j')]
    broker.service_instances = service_instances

    broker.services = ['x', 'y', 'z']

    deployer._enable_broker_access(broker)

    calls = [mock.call('c'), mock.call('j'), mock.call('x'), mock.call('y'), mock.call('z'),
             mock.call(broker.name)]
    for call in calls:
        assert call in mock_cf_cli.enable_service_access.call_args_list
    assert len(mock_cf_cli.enable_service_access.call_args_list) == len(calls)


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
    upsi_deployer._recreate_bindings = MagicMock()

    assert upsi_deployer._update(service_guid) == [SERVICE_BINDING['entity']['app_guid']]

    mock_cf_api.get_upsi_credentials.assert_called_with(service_guid)
    mock_cf_api.get_upsi_bindings.assert_called_with(service_guid)
    mock_cf_cli.update_user_provided_service(
        upsi_deployer.service.name, json.dumps(upsi_deployer.service.credentials))
    upsi_deployer._recreate_bindings.assert_called_with(service_bindings)


def test_update_upsi_not_needed(mock_cf_api, mock_cf_cli, upsi_deployer):
    service_guid = 'some-fake-guid'
    mock_cf_api.get_upsi_credentials.return_value = upsi_deployer.service.credentials

    assert upsi_deployer._update(service_guid) == []

    mock_cf_api.get_upsi_credentials.assert_called_with(service_guid)
    assert not mock_cf_api.get_upsi_bindings.call_args_list
    assert not mock_cf_cli.update_user_provided_service.call_args_list


def test_rebind_services(mock_cf_api, upsi_deployer):
    upsi_deployer._recreate_bindings([SERVICE_BINDING])

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


@pytest.fixture
def mock_get_file_path(monkeypatch):
    mock_get_file = MagicMock()
    monkeypatch.setattr('apployer.app_file.get_file_path', mock_get_file)
    return mock_get_file

def test_create_buildpack(monkeypatch, mock_cf_cli, mock_get_file_path):
    buildpack_name = 'some-buildpack'
    tools_dir = '/release/tools/'
    buildpack_path = tools_dir + 'some-buildpack-v1.2.3'
    monkeypatch.setattr('apployer.deployer._check_buildpack_needed',
                        MagicMock(side_effect=StopIteration))
    mock_get_file_path.return_value = buildpack_path

    deployer.setup_buildpack(buildpack_name, tools_dir)

    mock_get_file_path.assert_called_with(buildpack_name, tools_dir)
    mock_cf_cli.create_buildpack.assert_called_with(buildpack_name, buildpack_path)


def test_update_buildpack(monkeypatch, mock_cf_cli, mock_get_file_path):
    buildpack_name = 'some-buildpack'
    tools_dir = 'release/tools/'
    buildpack_path = tools_dir + 'some-buildpack-v1.2.3'
    monkeypatch.setattr('apployer.deployer._check_buildpack_needed', MagicMock(return_value=True))
    mock_get_file_path.return_value = buildpack_path

    deployer.setup_buildpack(buildpack_name, tools_dir)

    mock_cf_cli.update_buildpack.assert_called_with(buildpack_name, buildpack_path)
    assert not mock_cf_cli.create_buildpack.call_args_list


def test_check_buildpack_needed(mock_cf_cli):
    buildpack_name = 'some-buildpack'
    mock_cf_cli.buildpacks.return_value = [BuildpackDescription(buildpack_name, '1',
                                                                'true', 'false',
                                                                buildpack_name+'v1.2.3.zip')]

    assert deployer._check_buildpack_needed(buildpack_name, buildpack_name+'v1.0.0.zip')


def test_check_buildpack_needed_false(mock_cf_cli):
    buildpack_name = 'some-buildpack'
    buildpack_file = buildpack_name + '-v1.2.3.zip'
    buildpack_path = 'apps/' + buildpack_file
    mock_cf_cli.buildpacks.return_value = [BuildpackDescription(buildpack_name, '1', 'true',
                                                                'false', buildpack_file)]
    assert not deployer._check_buildpack_needed(buildpack_name, buildpack_path)


def test_setup_existing_buildpack(monkeypatch, mock_get_file_path):
    monkeypatch.setattr('apployer.deployer._check_buildpack_needed', MagicMock(return_value=False))
    deployer.setup_buildpack('some-buildpack-name', 'release/tools')


def test_deploy_appstack(monkeypatch, mock_upsi_deployer, mock_setup_broker):
    # arrange - data
    apps = [AppConfig('app1', register_in='application-broker'),
            AppConfig('application-broker')]
    user_provided_services = [UserProvidedService('upsi-name', {'a': 'b'})]
    brokers = [BrokerConfig('broker-name', 'http://broker-url', 'username', 'password')]
    buildpacks = ['fake-buildpack']
    security_groups = [SecurityGroup('sg-name', 'udp', '12.13.14.15/8', '56-139')]
    domain = 'fake-domain'
    appstack = AppStack(apps, user_provided_services, brokers,
                        buildpacks, domain, security_groups)

    cf_login_data = CfInfo('https://api.example.com', 'password')
    artifacts_path = 'some-fake-path'
    app_guids = ['app1-guid', 'application-broker-guid']
    is_dry_run = False

    # arrange - mocks
    mock_prep_org_and_space = MagicMock()
    monkeypatch.setattr('apployer.deployer._prepare_org_and_space', mock_prep_org_and_space)
    mock_upsi_deployer.return_value.deploy.return_value = [app_guids[0]]

    mock_setup_security_group = MagicMock()
    monkeypatch.setattr('apployer.deployer.setup_security_group', mock_setup_security_group)

    mock_setup_buildpack = MagicMock()
    monkeypatch.setattr('apployer.deployer.setup_buildpack', mock_setup_buildpack)

    mock_app_deployer_init, mock_app_deployer, mock_restart_apps = [MagicMock() for _ in range(3)]
    monkeypatch.setattr('apployer.deployer.AppDeployer', mock_app_deployer_init)
    mock_app_deployer_init.return_value = mock_app_deployer
    mock_app_deployer.deploy.side_effect = ([app_guids[1]], [])
    monkeypatch.setattr('apployer.deployer._restart_apps', mock_restart_apps)

    mock_register_in_app_broker = MagicMock()
    monkeypatch.setattr('apployer.deployer.register_in_application_broker',
                        mock_register_in_app_broker)

    # act
    deployer.deploy_appstack(cf_login_data, appstack, artifacts_path,
                             is_dry_run, deployer.UPGRADE_STRATEGY)

    # assert
    mock_prep_org_and_space.assert_called_with(cf_login_data)
    mock_upsi_deployer.assert_called_with(user_provided_services[0])
    mock_setup_broker.assert_called_with(brokers[0])
    mock_setup_buildpack.assert_called_with(buildpacks[0], artifacts_path)
    mock_setup_security_group.assert_called_once_with(cf_login_data, security_groups[0])

    app_deployer_init_calls = [mock.call(apps[0], deployer.DEPLOYER_OUTPUT),
                               mock.call(apps[1], deployer.DEPLOYER_OUTPUT)]
    assert app_deployer_init_calls == mock_app_deployer_init.call_args_list
    app_deployer_deploy_calls = [mock.call(artifacts_path, is_dry_run, deployer.UPGRADE_STRATEGY)
                                 for _ in range(2)]
    assert app_deployer_deploy_calls == mock_app_deployer.deploy.call_args_list

    mock_restart_apps.assert_called_with(appstack, app_guids)
    mock_register_in_app_broker.assert_called_with(apps[0], apps[1], domain,
                                                   deployer.DEPLOYER_OUTPUT, artifacts_path)


def test_deploy_appstack_dry_run(monkeypatch):
    fake_cf_login, fake_appstack, fake_artifacts_path, fake_is_dry_run, fake_strategy = 1, 2, 3, True, 4
    mock_do_deploy = MagicMock()
    monkeypatch.setattr('apployer.deployer._do_deploy', mock_do_deploy)
    real_cf_cli = deployer.cf_cli
    real_register_in_app_broker = deployer.register_in_application_broker

    deployer.deploy_appstack(fake_cf_login, fake_appstack, fake_artifacts_path,
                             fake_is_dry_run, fake_strategy)

    mock_do_deploy.assert_called_with(fake_cf_login, fake_appstack,
                                      fake_artifacts_path, fake_is_dry_run, fake_strategy)
    assert deployer.cf_cli is real_cf_cli
    assert deployer.register_in_application_broker is real_register_in_app_broker


def test_register_in_app_broker(monkeypatch, mock_check_call):
    # arrange
    app_env = {'display_name': 'blabla',
               'description': 'bleble',
               'image_url': 'lalalala'}
    some_app = AppConfig('app1', register_in='application-broker',
                         app_properties={'env': app_env})

    app_broker_env = {'AUTH_USER': 'some user',
                      'AUTH_PASS': 'some password'}
    app_broker = AppConfig('application-broker', app_properties={'env': app_broker_env})

    domain = 'fake-domain'
    artifacts_path = 'some-fake-path'
    unpacked_apps_dir = 'some/nonexisting/path'

    mock_app_deployer_init, mock_app_deployer = [MagicMock() for _ in range(2)]
    monkeypatch.setattr('apployer.deployer.AppDeployer', mock_app_deployer_init)
    mock_app_deployer_init.return_value = mock_app_deployer

    # act
    deployer.register_in_application_broker(some_app, app_broker, domain,
                                            unpacked_apps_dir, artifacts_path)

    # assert
    mock_app_deployer_init.assert_called_with(app_broker, unpacked_apps_dir)
    mock_app_deployer.prepare.assert_called_with(artifacts_path)
    # This doesn't check much - oh well. A thorough integration test would be useful.
    assert mock_check_call.call_args_list


def test_prepare_org_and_space(mock_cf_cli):
    api_uri = 'https://api.example.com'
    password = 'some password'
    user = 'some user'
    org = 'just some organization'
    space = 'a space from the organization above'
    ssl_validation = True
    cf_login_data = CfInfo(api_uri, password, user, org, space, ssl_validation)

    deployer._prepare_org_and_space(cf_login_data)

    mock_cf_cli.api.assert_called_with(api_uri, ssl_validation)
    mock_cf_cli.auth.assert_called_with(user, password)
    mock_cf_cli.create_org.assert_called_with(org)
    mock_cf_cli.create_space.assert_called_with(space, org)
    mock_cf_cli.target.assert_called_with(org, space)


def test_restart_apps(mock_cf_api, mock_cf_cli):
    apps = [AppConfig('app_1'), AppConfig('app_2'),
            AppConfig('app_3', push_options=PushOptions('--no-start'))]
    app_guids = ['app_1_guid', 'app_2_guid', 'app_3_guid']
    appstack = AppStack(apps)
    mock_cf_api.get_app_name.side_effect = [app.name for app in apps]

    deployer._restart_apps(appstack, app_guids)

    mock_cf_cli.restart.call_args_list == [mock.call(apps[0].name), mock.call(apps[1].name)]


def test_is_push_enabled():

    true_values = [True, 'true', 'TRUE', 'True']
    false_values = [False, 'false', 'FALSE', 'False']
    exception_values = [12, object, None, '', 'bad_string']

    for value in true_values:
        assert deployer.is_push_enabled(value) is True

    for value in false_values:
        assert deployer.is_push_enabled(value) is False

    for value in exception_values:
        with pytest.raises(Exception):
            deployer.is_push_enabled(value)


def test_setup_security_group(mock_cf_cli):
    api_uri = 'https://api.example.com'
    password = 'some password'
    user = 'some user'
    org = 'just some organization'
    space = 'a space from the organization above'
    ssl_validation = True
    cf_login_data = CfInfo(api_uri, password, user, org, space, ssl_validation)

    security_group = SecurityGroup('sg-name', 'udp', '12.13.14.15/8', '56-139')

    deployer.setup_security_group(cf_login_data, security_group)

    mock_cf_cli.create_security_group.assert_called_with(security_group.name,
                                                         deployer.SG_RULES_FILENAME)
    mock_cf_cli.bind_security_group(security_group.name, cf_login_data.org, cf_login_data.space)
