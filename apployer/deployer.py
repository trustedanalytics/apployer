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

"""
Code responsible for initiating and carrying out the deployment of applications, services and
brokers.
"""

import glob
import json
import logging
from os import path, remove
import subprocess
from zipfile import ZipFile

import datadiff
from pkg_resources import parse_version
import yaml

import apployer.app_file as app_file
from apployer import cf_cli, cf_api, dry_run
from .cf_cli import CommandFailedError

_log = logging.getLogger(__name__) #pylint: disable=invalid-name

UPGRADE_STRATEGY = 'UPGRADE'
PUSH_ALL_STRATEGY = 'PUSH_ALL'

UNPACKED_ARTIFACTS_FOLDER = 'apps'
FINAL_MANIFESTS_FOLDER = 'manifests'

DEPLOYER_OUTPUT = 'apployer_out'

SG_RULES_FILENAME = 'set-access.json'

def deploy_appstack(cf_login_data, filled_appstack, artifacts_path, is_dry_run, push_strategy):
    """Deploys the appstack to Cloud Foundry.

    Args:
        cf_login_data (`apployer.cf_cli.CfInfo`): Credentials and addresses needed to log into
            Cloud Foundry.
        filled_appstack (`apployer.appstack.AppStack`): Expanded appstack filled with configuration
            extracted from a live TAP environment.
        artifacts_path (str): Path to a directory containing application artifacts (zips).
        push_strategy (str): Strategy for pushing applications.
        is_dry_run (bool): Is this a dry run? If set to True, no changes (except for creating org
            and space) will be introduced to targeted Cloud Foundry.
    """
    global cf_cli, register_in_application_broker #pylint: disable=C0103,W0603,W0601

    if is_dry_run:
        normal_cf_cli = cf_cli
        cf_cli = dry_run.get_dry_run_cf_cli()
        normal_register_in_app_broker = register_in_application_broker
        register_in_application_broker = dry_run.get_dry_function(register_in_application_broker)
    try:
        _do_deploy(cf_login_data, filled_appstack, artifacts_path, is_dry_run, push_strategy)
    finally:
        if is_dry_run:
            cf_cli = normal_cf_cli
            register_in_application_broker = normal_register_in_app_broker


def _do_deploy(cf_login_data, filled_appstack, artifacts_path, is_dry_run, push_strategy):
    """Iterates over each CF entity defined in filled_appstack
    and executes CF commands necessery for deployment.

    Args:
        cf_login_data (`apployer.cf_cli.CfInfo`): Credentials and addresses needed to log into
            Cloud Foundry.
        filled_appstack (`apployer.appstack.AppStack`): Expanded appstack filled with configuration
            extracted from a live TAP environment.
        artifacts_path (str): Path to a directory containing application artifacts (zips).
        is_dry_run (bool): When enabled then all write commands to CF will be only logged.
        push_strategy (str): Strategy for pushing applications.
    """
    _prepare_org_and_space(cf_login_data)

    apps_to_restart = []

    for security_group in filled_appstack.security_groups:
        if is_push_enabled(security_group.push_if):
            setup_security_group(cf_login_data, security_group)

    for service in filled_appstack.user_provided_services:
        if is_push_enabled(service.push_if):
            affected_apps = UpsiDeployer(service).deploy()
            apps_to_restart.extend(affected_apps)

    for broker in filled_appstack.brokers:
        if is_push_enabled(broker.push_if):
            setup_broker(broker)

    for buildpack in filled_appstack.buildpacks:
        setup_buildpack(buildpack, artifacts_path)

    names_to_apps = {app.name: app for app in filled_appstack.apps}

    for app in filled_appstack.apps:
        if is_push_enabled(app.push_if):
            app_deployer = AppDeployer(app, DEPLOYER_OUTPUT)
            affected_apps = app_deployer.deploy(artifacts_path, is_dry_run, push_strategy)
            apps_to_restart.extend(affected_apps)
            if app.register_in:
                # FIXME this universal mechanism is kind of pointless, because we can only do
                # registering in application-broker. Even we made "register.sh" in the registrator
                # app to be universal, we still need to pass a specific set of arguments to the
                # script.
                # And those are arguments wanted by the application-broker.
                registrator_name = app.register_in
                register_in_application_broker(
                    app,
                    names_to_apps[registrator_name],
                    filled_appstack.domain,
                    DEPLOYER_OUTPUT,
                    artifacts_path)
    _restart_apps(filled_appstack, apps_to_restart)
    _execute_post_actions(filled_appstack.post_actions, artifacts_path)

    _log.info('DEPLOYMENT FINISHED')


def is_push_enabled(value):
    """To ensure that value passed is a boolean value, not string (which in appstack.yml is
    possible)

    Args:
        value(bool or str): value from which covert to bool; should be bool or 'true' or
                            'false' case insensitive
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
        else:
            raise Exception("Incorrect string value: " + value + " ! Should be \"true\" or "
                                                                 "\"false\" (case insensitive)")

    raise Exception("Incorrect type: " + type(value) + " Should be bool or str.")


def register_in_application_broker(registered_app, # pylint: disable=function-redefined
                                   application_broker, app_domain,
                                   unpacked_apps_dir, artifacts_location):
    """Registers an application in another application that provides some special functionality.
    E.g. there's the application-broker app that registers another application as a broker.

    Args:
        registered_app (`apployer.appstack.AppConfig`): Application being registered.
        application_broker (`apployer.appstack.AppConfig`): Application doing the registering.
        app_domain (str): Address domain for TAP applications.
        unpacked_apps_dir (str): Directory with unpacked artifacts.
        artifacts_location (str): Location of unpacked application artifacts.
    """
    _log.info('Registering app %s in %s...', registered_app.name, application_broker.name)
    application_broker_url = 'http://{}.{}'.format(application_broker.name, app_domain)

    register_script_path = path.join(unpacked_apps_dir, application_broker.name, 'register.sh')
    if not path.exists(register_script_path):
        _log.debug("Registration script %s doesn't exist. Most probably, the artifact it's in "
                   "didn't need to be unpacked yet. Gonna do that now...")
        AppDeployer(application_broker, unpacked_apps_dir).prepare(artifacts_location)

    command = ['/bin/bash', register_script_path, '-b', application_broker_url,
               '-a', registered_app.name, '-n', registered_app.name,
               '-u', application_broker.app_properties['env']['AUTH_USER'],
               '-p', application_broker.app_properties['env']['AUTH_PASS']]

    app_env = registered_app.app_properties['env']
    display_name = app_env.get('display_name')
    if display_name:
        command.extend(['-s', display_name])
    description = app_env.get('description')
    if description:
        command.extend(['-d', description])
    image_url = app_env.get('image_url')
    if image_url:
        command.extend(['-i', image_url])
    if registered_app.register_config:
        command.extend(['-c', registered_app.register_config])

    _log.info('Running registration script: %s', ' '.join(command))
    subprocess.check_call(command)


def setup_broker(broker):
    """Sets up a broker.It will be created if it doesn't exist. It will be updated otherwise.
    All of its instances will be created if they don't already. Nothing will be done to them if
    they already exist.

    Args:
        broker (`apployer.appstack.BrokerConfig`): Configuration of a service broker.

    Raises:
        CommandFailedError: Failed to set up the broker.
    """
    _log.info('Setting up broker %s...', broker.name)
    broker_args = [broker.name, broker.auth_username, broker.auth_password, broker.url]
    if broker.name not in cf_cli.service_brokers():
        _log.info("Broker %s doesn't exist. Gonna create it now...", broker.name)
        cf_cli.create_service_broker(*broker_args)
    else:
        _log.info("Broker %s exists. Will update it...", broker.name)
        cf_cli.update_service_broker(*broker_args)

    _enable_broker_access(broker)

    for service_instance in broker.service_instances:
        setup_service_instance(broker, service_instance)


def _enable_broker_access(broker):
    """Enables service access to the needed services.
    If a broker has instances without "label" set, then the access will be set to the broker
    itself (cf enable-service-access <broker_name>).
    All instances that do have a label mark a different logical broker and access needs to be given
    to them (for each unique label: cf enable-service-access <label>).
    """
    try:
        _log.info('Enabling access to service %s...', broker.name)
        cf_cli.enable_service_access(broker.name)
    except CommandFailedError as ex:
        _log.warning("Failed to enable service access for broker %s.\nError: %s\n"
                     "Assuming the broker doesn't provide any service by itself...",
                     broker.name, str(ex))

    labels = [instance.label for instance in broker.service_instances]
    services = broker.services
    for name in set(labels + services):
        if name:
            _log.info("Enabling access to service %s... ", name)
            cf_cli.enable_service_access(name)


def setup_buildpack(buildpack_name, buildpacks_directory):
    """Sets up a buildpack. It will be updated if it exists. It will be created otherwise.
    Newly created buildpack is always put in the first place of platform's buildpacks' list.

    Args:
        buildpack_name (str): Name of the buildpack.
        buildpacks_directory (str): Path to a directory containing buildpacks.
            It can be found in a platform release package, "apps" subdirectory.

    Raises:
        CommandFailedError: Failed to set up the buildpack.
    """
    _log.info('Setting up buildpack %s...', buildpack_name)
    buildpack_path = app_file.get_file_path(buildpack_name, buildpacks_directory)

    try:
        if _check_buildpack_needed(buildpack_name, buildpack_path):
            _log.info('Buildpack %s exists, but in a different version. '
                      'Updating...', buildpack_name)
            cf_cli.update_buildpack(buildpack_name, buildpack_path)
        else:
            _log.info('Buildpack %s is already present on the environment in this version. '
                      'Skipping...', buildpack_path)
    except StopIteration:
        _log.info('Buildpack %s not found in Cloud Foundry, will create it...', buildpack_name)
        cf_cli.create_buildpack(buildpack_name, buildpack_path)


def _check_buildpack_needed(buildpack_name, buildpack_path):
    buildpack_description = next(buildpack_descr for buildpack_descr in cf_cli.buildpacks()
                                 if buildpack_descr.buildpack == buildpack_name)
    buildpack_filename = path.basename(buildpack_path)
    _log.debug('Buildpack in deployment package: %s; in environment: %s',
               buildpack_filename, buildpack_description.filename)
    return buildpack_filename != buildpack_description.filename


def setup_service_instance(broker, service_instance):
    """Sets up a service instance for a broker.

    Args:
        broker (`apployer.appstack.BrokerConfig`): Configuration of a service broker.
        service_instance (`apployer.appstack.ServiceInstance`): Instance to be created

    Raises:
        CommandFailedError: Failed to set up the service instance.
    """
    try:
        cf_cli.service(service_instance.name)
        _log.info('Service instance %s already exists, skipping it...', service_instance.name)
    except CommandFailedError as ex:
        _log.debug(str(ex))
        _log.info("Getting properties of a service (%s) failed, assuming it doesn't exist yet.\n"
                  "Gonna create the service now...", service_instance.name)
        broker_name = service_instance.label or broker.name
        cf_cli.create_service(broker_name, service_instance.plan, service_instance.name)
        _log.debug('Created instance %s of service %s.', service_instance.name, broker_name)


def _execute_post_actions(post_actions, artifacts_path):
    for post_action in post_actions:
        _log.info(str.format('Executing post action: {}', post_action.name))
        for command in post_action.commands:
            _log.info(str.format('Executing command: {}', command))
            cf_cli.run_command(command, work_dir=artifacts_path,
                               skip_output=False, shell=True)


class UpsiDeployer(object):
    """Does the setup of a single user-provided service instance.

    Attributes:
        service (`apployer.appstack.UserProvidedService`): Service's configuration from the filled
            expanded appstack.

    Args:
        service (`apployer.appstack.UserProvidedService`): See class attributes.
    """

    def __init__(self, service):
        self.service = service

    @staticmethod
    def _recreate_bindings(bindings):
        """Recreates the given service bindings..

        Args:
            bindings (list[dict]): List of dictionaries representing a binding.
                Binding has "metadata" and "entity" fields.
        """
        for binding in bindings:
            service_guid = binding['entity']['service_instance_guid']
            app_guid = binding['entity']['app_guid']
            _log.debug('Rebinding %s to %s...', service_guid, app_guid)

            cf_api.delete_service_binding(binding)
            cf_api.create_service_binding(service_guid, app_guid)

    def deploy(self):
        """Sets up a user provided service. It will be created if it doesn't exist.
        It will be updated if it exists and its credentials in the live environment are different
        than in appstack.

        Returns:
            list[str]: List of applications (their guids) that need to be restarted because of the
                update of this service. This list will be empty when there's nothing to restart.

        Raises:
            CommandFailedError: Failed to set up the service.
        """
        service_name = self.service.name
        _log.info('Setting up user provided service %s...', service_name)
        try:
            service_guid = cf_cli.get_service_guid(service_name)
            _log.info('User provided service %s has GUID %s.', service_name, service_guid)
        except CommandFailedError as ex:
            _log.debug(str(ex))
            _log.info("Failed to get GUID of user provided service %s, assuming it doesn't exist "
                      "yet. Gonna create it now...", service_name)
            cf_cli.create_user_provided_service(service_name,
                                                json.dumps(self. service.credentials))
            _log.debug('Created user provided service %s.', service_name)
            return []

        return self._update(service_guid)

    def _update(self, service_guid):
        """Updates the service if it's different in the appstack and in the live environment.

        Args:
            service_guid (str): GUID of a service.

        Returns:
            list[str]: List of applications (their guids) that need to be restarted because of the
                update of this service. This list will be empty when there's nothing to restart
        """
        service_name = self.service.name
        appstack_credentials = self.service.credentials
        live_credentials = cf_api.get_upsi_credentials(service_guid)

        if live_credentials != appstack_credentials:
            _log.info('User provided service %s is different in the live environment and appstack. '
                      'Will update it...', service_name)
            _log.debug('Service credentials differences:\n%s',
                       datadiff.diff(live_credentials, appstack_credentials,
                                     fromfile='live env', tofile='appstack'))
            cf_cli.update_user_provided_service(service_name, json.dumps(appstack_credentials))

            service_bindings = cf_api.get_upsi_bindings(service_guid)
            _log.info('Rebinding apps to service instance %s...', service_name)
            self._recreate_bindings(service_bindings)

            app_guids = [binding['entity']['app_guid'] for binding in service_bindings]
            return app_guids
        else:
            _log.info('Service %s already exists and is up-to-date. No need to do anything...',
                      service_name)
            return []


class AppDeployer(object):
    """Does the deployment of a single application.

    Attributes:
        app (`apployer.appstack.AppConfig`): Application's configuration from the filled
            expanded appstack.
        output_path (str): Output path for Apployer. Application artifacts will be unpacked there.

    Args:
        app (`apployer.appstack.AppConfig`): See class attributes.
        output_path (str): See class attributes.
    """

    FILLED_MANIFEST = 'filled_manifest.yml'

    # TODO it should throw some error on push that can be handled by the overall procedure.
    def __init__(self, app, output_path):
        self.app = app
        self.output_path = output_path

    def deploy(self, artifacts_location, is_dry_run, push_strategy=UPGRADE_STRATEGY):
        """Sets up the application in Cloud Foundry. This also sets up the broker (if one is
        defined) and user provided services (if they exist) defined in application's configuration
        in appstack. Any changes will be made only when needed.

        Args:
            artifacts_location (str): Path to a directory containing artifacts in ZIP format.
                There shouldn't be any non-artifact ZIP files there.
            is_dry_run (bool): When enabled then all write commands to CF will be only logged.
            push_strategy (str): Strategy for pushing the application.

        Returns:
            list[str]: List of applications (their guids) that need to be restarted because of
                updates of user-provided services provided by this applications.
                This list will be empty when there's nothing to restart.
        """
        is_push_needed = self._check_push_needed(push_strategy)

        _log.info('Setting up application %s...', self.app.name)
        self._push_app(artifacts_location, is_push_needed)

        apps_to_restart = []
        for service in self.app.user_provided_services:
            affected_apps = UpsiDeployer(service).deploy()
            apps_to_restart.extend(affected_apps)

        if is_push_needed and self.app.push_options.post_command:
            self._execute_post_command(is_dry_run)

        if self.app.broker_config:
            setup_broker(self.app.broker_config)

        return apps_to_restart

    def prepare(self, artifacts_location):
        """Prepares the application for deployment. It extracts the artifact and saves a full
        app manifest to the artifact directory for CF CLI to use.

        Returns:
            str: Path to the directory from which the application can be pushed to CF.
        """
        _log.debug('Preparing app artifact of app %s...', self.app.name)
        artifact_partial_path = path.join(artifacts_location, self.app.artifact_name)
        try:
            artifact_path = glob.glob('{}*'.format(artifact_partial_path))[0]
        except IndexError:
            raise IOError("Didn't find any artifact matching to path {}"
                          .format(artifact_partial_path))

        unpacked_path = path.realpath(path.join(self.output_path, self.app.name))

        _log.debug('Unpacking app artifact from %s to %s...', artifact_path, unpacked_path)
        ZipFile(artifact_path).extractall(unpacked_path)

        filled_manifest_path = path.join(unpacked_path, self.FILLED_MANIFEST)
        _log.debug('Dumping filled application manifest: %s', filled_manifest_path)
        with open(filled_manifest_path, 'w') as manifest_file:
            yaml.dump(
                {'applications': [self.app.app_properties]},
                manifest_file,
                default_flow_style=False,
                width=1000)

        return unpacked_path

    def _push_app(self, artifacts_location, is_push_needed):
        """Pushes an application to Cloud Foundry. Or not, if the conditions aren't right.
        Can also restart it.
        """
        if is_push_needed:
            _log.info('Pushing app %s...', self.app.name)
            prepared_app_path = self.prepare(artifacts_location)
            app_manifest_location = path.join(prepared_app_path, self.FILLED_MANIFEST)
            cf_cli.push(prepared_app_path, app_manifest_location, self.app.push_options.params)
        else:
            _log.info("No need to push app %s, it's already up-to-date...", self.app.name)

    def _check_push_needed(self, push_strategy):
        _log.debug('Checking whether to push app %s...', self.app.name)
        try:
            if push_strategy == PUSH_ALL_STRATEGY:
                _log.debug('Will push app %s because strategy is PUSH_ALL.', self.app.name)
            else:
                live_app_version = self._get_app_version()
                # empty version string will be parsed to the lowest possible version
                appstack_app_version = self.app.app_properties.get('env', {}).get('VERSION', '')
                if parse_version(live_app_version) >= parse_version(appstack_app_version):
                    _log.debug("App's version (%s) in the live environment isn't lower than the "
                               "one in filled appstack (%s).\nWon't push app %s",
                               live_app_version, appstack_app_version, self.app.name)
                    return False
                else:
                    _log.debug("App's version (%s) in the in filled appstack is higher than in "
                               "live environment (%s).\nWill push app %s",
                               appstack_app_version, live_app_version, self.app.name)
        except (CommandFailedError, AppVersionNotFoundError) as ex:
            _log.debug(str(ex))
            _log.debug("Getting app (%s) version failed. Will push the app because of that.",
                       self.app.name)
        return True

    def _get_app_version(self):
        app_env = cf_cli.env(self.app.name)
        try:
            app_version_line = next(line for line in app_env.splitlines()
                                    if line.startswith('VERSION:'))
        except StopIteration:
            raise AppVersionNotFoundError(
                "Can't determine the version of app {}. VERSION environment variable not found."
                .format(self.app.name))
        return app_version_line.split()[1]

    def _execute_post_command(self, is_dry_run):
        if is_dry_run:
            _log.info('DRY RUN: App %s has post-push commands, executing following command %s\n',
                      self.app.name, self.app.push_options.post_command)
        else:
            _log.info('App %s has post-push commands, executing...', self.app.name)
            subprocess.check_call(self.app.push_options.post_command, shell=True)


class AppVersionNotFoundError(Exception):
    """
    'VERSION' environment variable wasn't present for an application.
    """


def setup_security_group(cf_login_data, security_group):
    """Creates and binds security group to seedorg.

    Args:
        cf_login_data (`cf_cli.CfInfo`) CF infos containing org and space to which bind
                                        security group
        security_group (`apployer.SecurityGroup`): Definition of security group
    """

    security_group_arrayed = [security_group.to_dict_for_cf_json()]

    with open(SG_RULES_FILENAME, 'w') as file_pipe:
        json.dump(security_group_arrayed, file_pipe)

    cf_cli.create_security_group(security_group.name, SG_RULES_FILENAME)
    cf_cli.bind_security_group(security_group.name, cf_login_data.org, cf_login_data.space)

    remove(SG_RULES_FILENAME)


def _prepare_org_and_space(cf_login_data):
    """Logs into CloudFoundry and prepares organization and space for deployment.

    Args:
        cf_login_data (`apployer.cf_cli.CfInfo`): Credentials and addresses needed to log into
            Cloud Foundry.
    """
    cf_cli.api(cf_login_data.api_url, cf_login_data.ssl_validation)
    cf_cli.auth(cf_login_data.user, cf_login_data.password)
    cf_cli.create_org(cf_login_data.org)
    cf_cli.create_space(cf_login_data.space, cf_login_data.org)
    cf_cli.target(cf_login_data.org, cf_login_data.space)


def _restart_apps(filled_appstack, app_guids):
    """Restarts applications. These apps need to be restarted because some user-provided services
    bound to them have changed.

    Args:
        filled_appstack (`apployer.appstack.AppStack`): Expanded appstack filled with configuration
            extracted from a live TAP environment.
        app_guids (list[str]): Applications GUIDs.
    """
    app_names = [cf_api.get_app_name(app_guid) for app_guid in app_guids]

    for app_name in app_names:
        app = next(app for app in filled_appstack.apps if app.name == app_name)
        if '--no-start' not in app.push_options.params:
            _log.info("Restarting app %s because some of user-provided services bound to it have "
                      "changed...", app_name)
            cf_cli.restart(app_name)
        else:
            _log.info("Some of user-provided services bound to app %s have changed, but there's "
                      "no need to restart it, since it has the '--no-start' flag.", app_name)
