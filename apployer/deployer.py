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
from os import path
import subprocess
from zipfile import ZipFile

from pkg_resources import parse_version
import yaml

import apployer.app_file as app_file
from apployer import cf_cli
from .cf_cli import CommandFailedError

_log = logging.getLogger(__name__) #pylint: disable=invalid-name

UPGRADE_STRATEGY = 'UPGRADE'
PUSH_ALL_STRATEGY = 'PUSH_ALL'

UNPACKED_ARTIFACTS_FOLDER = 'apps'
FINAL_MANIFESTS_FOLDER = 'manifests'

DEPLOYER_OUTPUT = 'apployer_out'


# TODO add option of dry run that switches all cf_cli commands to stubs
def deploy_appstack(cf_login_data, filled_appstack, artifacts_path,
                    push_strategy, ignore_errors=False):
    """Deploys the appstack to Cloud Foundry.

    Args:
        cf_login_data (`apployer.cf_cli.CfInfo`): Credentials and addresses needed to log into
            Cloud Foundry.
        filled_appstack (`apployer.appstack.AppStack`): Expanded appstack filled with configuration
            extracted from a live TAP environment.
        artifacts_path (str): Path to a directory containing application artifacts (zips).
        push_strategy (str): Strategy for pushing applications.
        ignore_errors (bool): If set to True errors won't stop deployment.
    """
    _prepare_org_and_space(cf_login_data)

    for service in filled_appstack.user_provided_services:
        run_ignoring_errors(ignore_errors, setup_user_provided_service, service)

    for broker in filled_appstack.brokers:
        run_ignoring_errors(ignore_errors, setup_broker, broker)

    for buildpack in filled_appstack.buildpacks:
        run_ignoring_errors(ignore_errors, setup_buildpack, buildpack, artifacts_path)

    for app in filled_appstack.apps:
        AppDeployer(app, DEPLOYER_OUTPUT, ignore_errors).deploy(artifacts_path, push_strategy)

    names_to_apps = {app.name: app for app in filled_appstack.apps}
    for app in filled_appstack.apps:
        if app.register_in:
            # FIXME this universal mechanism is kind of pointless, because we can only do
            # registering in application-broker. Even we made "register.sh" in the registrator app
            # to be universal, we still need to pass a specific set of arguments to the script.
            # And those are arguments wanted by the application-broker.
            registrator_name = app.register_in
            run_ignoring_errors(ignore_errors, register_in_application_broker, app,
                                names_to_apps[registrator_name], filled_appstack.domain,
                                DEPLOYER_OUTPUT, artifacts_path)

    _log.info('DEPLOYMENT FINISHED')


def run_ignoring_errors(ignore, func, *args, **kwargs):
    """Runs a given function with the option of catching all of its exceptions and logging them.

    Args:
        ignore (bool): Whether to catch exceptions. If set to True, no exceptions will be raised
            from this function. If set to False, exceptions from the target function will be
            normally propagated to the program.
        func: Function to run.
        *args: Function's positional arguments.
        **kwargs: Function's keyword arguments.

    Returns:
        Whatever `func` returns.
    """
    try:
        return func(*args, **kwargs)
    except Exception as ex: # pylint: disable=broad-except
        if ignore:
            _log.exception('Ignoring an error...')
        else:
            raise ex


class AppVersionNotFoundError(Exception):
    """
    'VERSION' environment variable wasn't present for an application.
    """


# TODO test
def register_in_application_broker(registered_app, application_broker, app_domain,
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
    _log.info('Updating broker %s...', broker.name)
    broker_args = [broker.name, broker.auth_username, broker.auth_password, broker.url]
    try:
        cf_cli.update_service_broker(*broker_args)
    except CommandFailedError as ex:
        _log.debug(str(ex))
        _log.info("Updating a broker (%s) failed, assuming it doesn't exist yet. "
                  "Gonna create it now...", broker.name)
        cf_cli.create_service_broker(*broker_args)

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
    for name in set(labels):
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
        _log.info('Buildpack %s not found, will create it...', buildpack_name)
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


def setup_user_provided_service(service):
    """Sets up a user provided service. It will be updated if it exists, it will be created
    otherwise.

    Args:
        service (`apployer.appstack.UserProvidedService`): Configuration of a user provided
            service.

    Raises:
        CommandFailedError: Failed to set up the service.
    """
    _log.info('Updating user provided service %s...', service.name)
    service_args = (service.name, json.dumps(service.credentials))
    try:
        cf_cli.update_user_provided_service(*service_args)
    except CommandFailedError as ex:
        _log.debug(str(ex))
        _log.info("Failed to update user provided service (%s), assuming it doesn't exist yet.\n"
                  "Gonna create it now...", service.name)
        cf_cli.create_user_provided_service(*service_args)
        _log.debug('Created user provided service %s.', service.name)


class AppDeployer(object):
    """Does the deployment of a single application.

    Attributes:
        app (`apployer.appstack.AppConfig`): Application's configuration from the filled
            expanded appstack.
        output_path (str): Output path for Apployer. Application artifacts will be unpacked there.
        ignore_errors (bool): If set to True errors won't stop deployment.
    """

    FILLED_MANIFEST = 'filled_manifest.yml'

    # TODO it should throw some error on push that can be handled by the overall procedure.
    def __init__(self, app, output_path, ignore_errors=False):
        self.app = app
        self.output_path = output_path
        self.ignore_errors = ignore_errors

    def deploy(self, artifacts_location, push_strategy=UPGRADE_STRATEGY):
        """Sets up the application in Cloud Foundry. This also sets up the broker (if one is
        defined) and user provided services (if they exist) defined in application's configuration
        in appstack. Any changes will be made only when needed.

        Args:
            artifacts_location (str): Path to a directory containing artifacts in ZIP format.
                There shouldn't be any non-artifact ZIP files there.
            push_strategy (str): Strategy for pushing the application.
        """
        _log.info('Setting up application %s...', self.app.name)
        if self._exists():
            run_ignoring_errors(self.ignore_errors, self._rebind_services)

        run_ignoring_errors(self.ignore_errors, self._push_app, artifacts_location, push_strategy)
        for service in self.app.user_provided_services:
            run_ignoring_errors(self.ignore_errors, setup_user_provided_service, service)
        if self.app.broker_config:
            run_ignoring_errors(self.ignore_errors, setup_broker, self.app.broker_config)

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

    def _exists(self):
        """
        Returns:
            bool: True if the app is already present on the live environment. False otherwise
        """
        try:
            cf_cli.env(self.app.name)
            _log.debug('App %s exists.', self.app.name)
            return True
        except CommandFailedError as ex:
            _log.debug("App %s doesn't exists.\n%s", self.app.name, str(ex))
            return False

    def _rebind_services(self):
        """Rebinds all services that this apps depends on.

        User provided services might have been changed during the deployment up to this moment.
        We cannot determine what services have really been modified without some global state
        and we want to avoid having that.
        So, as a precaution, we rebind everything.

        Once listing of service bindings for a particular user provided service if provided through
        some CF API client, then it could be more elegant.
        """
        app_name = self.app.name
        _log.info('Rebinding service instances for app %s...', app_name)
        for service_name in self.app.app_properties.get('services', []):
            _log.debug('Rebinding %s to %s...', service_name, app_name)
            cf_cli.unbind_service(app_name, service_name)
            cf_cli.bind_service(app_name, service_name)

    def _push_app(self, artifacts_location, push_strategy):
        """Pushes an application to Cloud Foundry. Or not, if the conditions aren't right.
        Can also restart it.
        """
        def _do_push():
            _log.info('Pushing app %s...', self.app.name)
            prepared_app_path = self.prepare(artifacts_location)
            app_manifest_location = path.join(prepared_app_path, self.FILLED_MANIFEST)
            cf_cli.push(prepared_app_path, app_manifest_location, self.app.push_options.params)

        if self._check_push_needed(push_strategy):
            _do_push()
        elif '--no-start' in self.app.push_options.params:
            _log.info("No need to push or restart app %s. It's already in good version and it's "
                      "not meant to be started.", self.app.name)
        else:
            _log.info('No need to push app %s. Restarting it so it can load new service configs...',
                      self.app.name)
            try:
                cf_cli.restart(self.app.name)
            except CommandFailedError as ex:
                _log.warning('Failed to restart an application. Will try to push it...'
                             '\nRestart error: %s', str(ex))
                _do_push()
        if self.app.push_options.post_command:
            _log.info('App %s has post-push commands, executing...', self.app.name)
            subprocess.check_call(self.app.push_options.post_command, shell=True)

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
