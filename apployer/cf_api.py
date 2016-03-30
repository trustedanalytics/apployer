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

# Those descriptions may come in handy at one point in time.
# bastion_host (str): Host of the bastion machine that has access to the outside world and
#     Cloud Foundry cluster. This machine should have the configuration files left over from
#     deploying Cloud Foundry, CDH, etc. This configuration has to be read to fill out some
#     configuration values in the expanded appstack.
# cdh_bastion_host (str): Host of bastion machine bridging the outside world and CDH cluster
#     machines. If not set will default to `bastion_host`.

"""
Cloud Foundry REST API client wrapping "cf curl" command.
WARNING: Functions used here must be used AFTER logging in to cloud foundry with functions
from `apployer.cf_cli`
"""

import json

from apployer import cf_cli

CF_CURL = [cf_cli.CF, 'curl']


def create_service_binding(service_guid, app_guid):
    """Creates a binding between a service and an application.

    Args:
        service_guid (str): GUID of a service instance (can be user-provided).
        app_guid (str): Applications' GUID.
    """
    params = {'service_instance_guid': service_guid, 'app_guid': app_guid}
    command_suffix = ['/v2/service_bindings', '-X', 'POST', '-d', json.dumps(params)]
    cmd_output = cf_cli.get_command_output(CF_CURL + command_suffix)
    response_json = json.loads(cmd_output)
    if 'error_code' not in response_json:
        return response_json
    else:
        raise cf_cli.CommandFailedError(
            'Failed to create a binding between service {} and app {}.\n'
            'Response body: {}'.format(service_guid, app_guid, response_json))


def delete_service_binding(binding):
    """Deletes a service binding.

    Args:
        binding (dict): JSON representing a service binding. Has "metadata" and "entity" keys.
    """
    binding_url = binding['metadata']['url']
    cmd_output = cf_cli.get_command_output(CF_CURL + [binding_url, '-X', 'DELETE'])
    if cmd_output:
        raise cf_cli.CommandFailedError('Failed to delete a service binding. CF response: {}'
                                        .format(cmd_output))

def get_app_name(app_guid):
    """
    Args:
        app_guid (str): Application's GUID.

    Returns:
        str: Application's name,
    """
    app_desctiption = _cf_curl_get('/v2/apps/{}'.format(app_guid))
    return app_desctiption['entity']['name']


def get_upsi_credentials(service_guid):
    """Gets the credentials (configuration) of a user-provided service instance.

    Args:
        service_guid (str): Service instance's GUID.

    Returns:
        dict: Content of the instance's "credentials" dictionary.
    """
    api_path = '/v2/user_provided_service_instances/{}'.format(service_guid)
    upsi_description = _cf_curl_get(api_path)
    return upsi_description['entity']['credentials']


def get_upsi_bindings(service_guid):
    """Gets the bindings of a given user provided service instance.

    Args:
        service_guid (str): Service instance's GUID.

    Returns:
        list[dict]: List of dictionaries representing a binding.
            Binding has "metadata" and "entity" fields.
    """
    api_path = '/v2/user_provided_service_instances/{}/service_bindings'.format(service_guid)
    bindings_response = _cf_curl_get(api_path)
    return bindings_response['resources']


def _cf_curl_get(path):
    """Calls "cf curl" with a given path.

    Args:
        path (str): CF API path,
            e.g. /v2/user_provided_service_instances/8b89a54b-b292-49eb-a8c4-2396ec038120

    Returns:
        dict: JSON returned by the endpoint.
    """
    cmd_output = cf_cli.get_command_output(CF_CURL + [path])
    response_json = json.loads(cmd_output)
    if 'error_code' not in response_json:
        return response_json
    else:
        raise cf_cli.CommandFailedError('Failed GET on CF API path {}\n'
                                        'Response body: {}'.format(path, response_json))
