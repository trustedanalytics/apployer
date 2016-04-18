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
Providing an elegant option of a dry run for the Apployer.
"""

import inspect
import logging
import types

from apployer import cf_cli

_log = logging.getLogger(__name__) #pylint: disable=invalid-name


def get_dry_run_cf_cli():
    """Providing a module with functions having identical signatures as functions in cf_cli.
    Functions that don't introduce any changes to Cloud Foundry (with the exception of those that
    create the org and space) will remain, others will just log their names and parameters."""
    function_exceptions = ['login', 'buildpacks', 'create_org', 'create_space', 'env',
                           'get_app_guid', 'get_service_guid', 'oauth_token', 'service', 'service_brokers',
                           'api', 'auth', 'target', 'get_command_output']
    return provide_dry_run_module(cf_cli, function_exceptions)


def provide_dry_run_module(module, exceptions):
    """Provides a new module with functions having identical signatures as functions in the
    provided module. Public functions (the ones not starting with "_") in the new module do nothing
    but log their parameters and the name of the original function.
    Non-public functions act the same like in the old module.

    Args:
        module (`types.ModuleType`): A module to create a "dry-run" version of.
        exceptions (`list[str]`): A list of functions that shouldn't be modified. They will retain
            their normal behavior and effects in the new module.
    """
    module_functions = [member for member in inspect.getmembers(module)
                        if inspect.isfunction(member[1])]
    dry_run_module = types.ModuleType('dry_run_' + module.__name__)

    exceptions_set = set(exceptions)
    for name, function in module_functions:
        if name.startswith('_') or name in exceptions_set:
            setattr(dry_run_module, name, function)
        else:
            setattr(dry_run_module, name, get_dry_function(function))
    return dry_run_module


def get_dry_function(function):
    """Returns a substitute for a given function. The substitute logs the name of the original
    function and the parameters given to it.

    Args:
        function (types.FunctionType): Function to be substituted.

    Returns:
        types.FunctionType: The substitute function.
    """
    def _wrapper(*args, **kwargs):
        _log.info('DRY RUN: calling %s with arguments %s',
                  function.__name__, inspect.getcallargs(function, *args, **kwargs))
    return _wrapper
