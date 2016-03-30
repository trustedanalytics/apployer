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
Wrapper for command line tool "cf".
"""

from collections import namedtuple
import logging
from subprocess import Popen, PIPE, STDOUT


CF = 'cf'
_log = logging.getLogger(__name__) # pylint: disable=invalid-name


BuildpackDescription = namedtuple('BuildpackDescription',
                                  ['buildpack', 'position', 'enabled', 'locked', 'filename'])


class CommandFailedError(Exception):
    """
    Command carried out by CF CLI has failed.
    """
    pass


class CfInfo(object):
    """Information needed to log into Cloud Foundry.

    Attributes:
        api_url (str): CF API URL. This must point to raw Cloud Controller, not to an endpoint
            connected to auth-gateway.
        password (str): Password for the Cloud Foundry user.
        user (str): Cloud Foundry user that this tool act as.
        org (str): Organization in which everything should be deployed.
        space (str): Space in the organization.
        ssl_validation (bool): Should the SSL (actually TLS) connection to CF API be validated.
    """

    def __init__(self, api_url, password,  # pylint: disable=too-many-arguments
                 user='admin', org='seedorg', space='seedspace',
                 ssl_validation=False):
        self.api_url = api_url
        self.password = password
        self.user = user
        self.org = org
        self.space = space
        self.ssl_validation = ssl_validation


def login(cf_info):
    """Logs the CF CLI into a Cloud Foundry instance specified in the constructor.

    Args:
        cf_info (CfInfo): Cloud Foundry instance access information.

    Raises:
        CommandFailedError: When there are errors in any of the subcommands (api, auth, target)
    """
    api(cf_info.api_url, cf_info.ssl_validation)
    auth(cf_info.user, cf_info.password)
    target(cf_info.org, cf_info.space)


def bind_service(app_name, instance_name):
    """Binds a service instance to an application.
    Args:
        app_name (str): Name of an application.
        instance_name (str): Name of a service instance.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'bind-service', app_name, instance_name])


def buildpacks():
    """
    Returns:
        list[`BuildpackDescription`]: A list of buildpacks on the environment.
    """
    out = _get_command_output([CF, 'buildpacks'])
    buildpack_lines = out.splitlines()[3:]
    return [BuildpackDescription(*buildpack_line.split()) for buildpack_line in buildpack_lines]


def unbind_service(app_name, instance_name):
    """Unbinds a service instance from an application.
    Args:
        app_name (str): Name of an application.
        instance_name (str): Name of a service instance.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'unbind-service', app_name, instance_name])


def create_buildpack(buildpack_name, buildpack_path, position=1):
    """Creates a buildpack. Always enables it afterwards (--enable flag).

    Args:
        buildpack_name (str): Name for the buildpack.
        buildpack_path (str): Path to the buildpack's artifact.
        position (int): Priority of the new buildpack in the buildpack list.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'create-buildpack',
                  buildpack_name, buildpack_path, str(position), '--enable'])


def create_org(org_name):
    """Creates a new organization. Will do nothing if it's already created.

    Args:
        org_name (str): Name for the organization.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'create-org', org_name])


def create_service(broker, plan, instance_name):
    """Creates a service instance.

    Args:
        broker (str): Name of the broker (service) from marketplace.
        plan (str): Service plan from which the instance will be created.
        instance_name (str): Name of the created instance.

    Raises:
        CommandFailedError: When "cf create-service" fails (returns non-zero code).
    """
    _run_command([CF, 'create-service', broker, plan, instance_name])


def create_service_broker(name, user, password, url):
    """Creates a service broker.

    Args:
        name (str): Name of the new broker.
        user (str): Username that can be used to authorize with the broker.
        password (str): Password that can be used to authorize with the broker.
        url (str): HTTP address under which the broker will be available.

    Raises:
        CommandFailedError: When "cf create-service-broker" fails (returns non-zero code).
    """
    _run_command([CF, 'create-service-broker', name, user, password, url])


def create_space(space_name, org_name):
    """Creates a new space within an organization. Will do nothing if it's already created.

    Args:
        space_name (str): Name for the space.
        org_name (str): Name for the organization.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'create-space', space_name, '-o', org_name])


def create_user_provided_service(service_name, credentials):
    """Creates a user provided service.

    Args:
        service_name (str): Name for the service instance.
        credentials (str): String containing a serialized JSON with the values that this service
            will hold.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'create-user-provided-service', service_name, '-p', credentials])


def enable_service_access(broker):
    """Enables access to every plan of a service broker for every organization.

    Args:
        broker (str): Name of the broker (service).

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'enable-service-access', broker])


def env(app_name):
    """
    Args:
        app_name (str): Application's name.

    Returns:
        str: Application's environment configuration as string.
    """
    return _get_command_output([CF, 'env', app_name])


def oauth_token():
    """
    Returns:
        str: User's OAuth token.
    """
    command_out = _get_command_output([CF, 'oauth-token'])
    return command_out.splitlines()[-1]


def push(app_location, manifest_location, options='', timeout=180):
    """Push an application to Cloud Foundry.
    Args:
        app_location (str): Path to directory containing application's files.
        manifest_location (str): Path to a manifest the application should be pushed with.
        options (str): String with additional options for "cf push" command.
        timeout (int): Push timeout.

    Raises:
        CommandFailedError: "cf push" failed.
    """
    command = [CF, 'push', '-t', str(timeout), '-f', manifest_location] + options.split()
    _run_command(command, work_dir=app_location, redirect_output=False)


def restage(app_name):
    """Restage an application.

    Args:
        app_name (str): Name of the application to restage.

    Raises:
        CommandFailedError: "cf restage" failed (returned non-zero code).
    """
    _run_command([CF, 'restage', app_name], redirect_output=False)


def restart(app_name):
    """Restart an application.

    Args:
        app_name (str): Name of the application to restart.

    Raises:
        CommandFailedError: "cf restart" failed (returned non-zero code).
    """
    _run_command([CF, 'restart', app_name], redirect_output=False)


def service(service_name):
    """
    Args:
        service_name (str): Service's name.

    Returns:
        str: Service instance info.
    """
    return _get_command_output([CF, 'service', service_name])


def update_buildpack(buildpack_name, buildpack_path):
    """Updates a buildpack.

    Args:
        buildpack_name (str): Name for the buildpack.
        buildpack_path (str): Path to the buildpack's artifact.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'update-buildpack', buildpack_name, '-p', buildpack_path])


def update_service_broker(name, user, password, url):
    """Updates a service broker.

    Args:
        name (str): Name of the broker.
        user (str): Username that can be used to authorize with the broker.
        password (str): Password that can be used to authorize with the broker.
        url (str): HTTP address under which the broker will be available.

    Raises:
        CommandFailedError: When "cf update-service-broker" fails (returns non-zero code).
    """
    _run_command([CF, 'update-service-broker', name, user, password, url])


def update_user_provided_service(service_name, credentials):
    """Updates a user provided service.

    Args:
        service_name (str): Name of the service instance.
        credentials (str): String containing a serialized JSON with the values that this service
            will hold.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'update-user-provided-service', service_name, '-p', credentials])


def api(api_url, ssl_validation):
    """Set target Cloud Foundry API URL for the CF CLI commands.

    Args:
        api_url (str): CF API URL.
        ssl_validation (bool): Should the SSL (actually TLS) connection to CF API be validated.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    command = [CF, 'api', api_url]
    if not ssl_validation:
        command.insert(-1, '--skip-ssl-validation')
    proc = Popen(command)
    if proc.wait() != 0:
        raise CommandFailedError('Command failed: {}'.format(' '.join(command)))


def auth(username, password):
    """Logs into CF CLI as a specific user.

    Args:
        username (str):
        password (str):

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    proc = Popen([CF, 'auth', username, password])
    if proc.wait() != 0:
        raise CommandFailedError('Failed to login user: {}'.format(username))


def target(org, space):
    """Set target organization and space for the CF CLI commands.

    Args:
        org (str): Organization in which everything should be deployed.
        space (str): Space in the organization.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    _run_command([CF, 'target', '-o', org, '-s', space])


def _run_command(command, work_dir='.', redirect_output=True):
    """Runs a generic command without capturing its output.

    Args:
        command (list[str]): List of command parts (like in constructor of Popen)
        work_dir (str): Working directory in which the command should be run.
        redirect_output (bool): If set to True, standard and and error outputs of the process will
            be captured. Otherwise, they'll go to output of Apployer's process.

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    if redirect_output:
        proc = Popen(command, stdout=PIPE, stderr=STDOUT, cwd=work_dir)
        if proc.wait() != 0:
            raise CommandFailedError('Failed command: {}\nOutput: {}'
                                     .format(' '.join(command), proc.stdout.read()))
    else:
        proc = Popen(command, cwd=work_dir)
        if proc.wait() != 0:
            raise CommandFailedError('Failed command: {}'.format(' '.join(command)))


def _get_command_output(command):
    """Gets output of a generic command.

    Args:
        command (list[str]): List of command parts (like in constructor of Popen)

    Raises:
        CommandFailedError: When the command fails (returns non-zero code).
    """
    proc = Popen(command, stdout=PIPE)
    return_code = proc.wait()
    output = proc.stdout.read()

    if return_code == 0:
        return output
    else:
        raise CommandFailedError('Failed command: {}\nOutput: {}'.format(' '.join(command), output))
