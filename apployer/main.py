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
CLI for apployer.
"""

import logging
import os
import sys
import time

import click
import yaml

import apployer
from .appstack import AppStack
from .appstack_expand import expand_appstack
from .deployer import deploy_appstack, UPGRADE_STRATEGY
from apployer.cf_cli import CfInfo
from .fetcher import fill_appstack, DEFAULT_FETCHER_CONF, DEFAULT_FILLED_APPSTACK_PATH

DEFAULT_EXPANDED_APPSTACK_FILE = 'expanded_appstack.yml'
DEFAULT_APPSTACK_FILE = 'appstack.yml'

_log = logging.getLogger(__name__) #pylint: disable=invalid-name


@click.group()
@click.option('-v', '--verbose', is_flag=True,
              help='Enable debug output.')
def cli(verbose):
    """
    Apployer - deploying applications and stuff.
    """
    if verbose:
        _setup_logging(logging.DEBUG)
    else:
        _setup_logging(logging.INFO)


@cli.command()
@click.argument('ARTIFACTS_LOCATION')
@click.argument('APPSTACK_FILE', required=False, default=DEFAULT_APPSTACK_FILE)
@click.argument('EXPANDED_APPSTACK_LOCATION',
                default=DEFAULT_EXPANDED_APPSTACK_FILE, required=False)
def expand(appstack_file, artifacts_location, expanded_appstack_location):
    """
    Merges the manifests from app artifacts in appstack creating an expanded appstack that can be
    added to TAP release package. Applications in expanded appstack are sorted according to
    their proper deployment order.


    ARTIFACTS_LOCATION: Path to a directory with applications' artifacts (zips).
    It should be the "apps/" subdirectory of an unpacked TAP release package.

    APPSTACK_FILE defaults to "appstack.yml".

    EXPANDED_APPSTACK_LOCATION defaults to "expanded_appstack.yml".
    """
    expand_appstack(appstack_file, artifacts_location, expanded_appstack_location)


@cli.command()
@click.argument('ARTIFACTS_LOCATION')
@click.argument('CF_API_ENDPOINT')
@click.option('-u', '--cf-user',
              default='admin', show_default=True,
              help="Cloud Foundry user on who's behalf we'll deploy appstack.")
@click.option('-p', '--cf-password', prompt=True, hide_input=True,
              help="User's password for Cloud Foundry instance.")
@click.option('-o', '--cf-org',
              default='seedorg', show_default=True,
              help="Cloud Foundry organization to deploy apps to.")
@click.option('-s', '--cf-space',
              default='seedspace', show_default=True,
              help="Cloud Foundry space to deploy apps to.")
@click.option('-f', '--fetch-conf', 'fetcher_config',
              default=DEFAULT_FETCHER_CONF, show_default=True,
              help='Path to the configuration file for environment configuration fetcher.')
@click.option('-l', '--filled-appstack',
              default=DEFAULT_FILLED_APPSTACK_PATH,
              help="Path to the file containing expanded appstack filled with configuration taken "
                   "from live TAP environment that we want to deploy to. If it doesn't exist, then "
                   "Apployer will fallback to --expanded-appstack and fetch configuration from the "
                   "environment. After fetching filled expanded appstack will be saved to this "
                   "location.")
@click.option('-e', '--expanded-appstack',
              default=DEFAULT_EXPANDED_APPSTACK_FILE,
              help="Path to the file containing the expanded appstack definition. "
                   "It's not used if --filled-appstack exists. "
                   "If it doesn't exist, then Apployer will fallback to --appstack and do the "
                   "expansion. After expansion, expanded appstack will be saved in this location.")
@click.option('-a', '--appstack',
              default=DEFAULT_APPSTACK_FILE, show_default=True,
              help='Path to the file containing non-expanded appstack. Only used if expanded'
                   'appstack has not been specified.')
@click.option('--push-strategy',
              default=UPGRADE_STRATEGY, show_default=True,
              help="Strategy for pushing the applications.\n"
                   "'UPGRADE': deploy everything that doesn't exist in the environment or is in "
                   "lower version on the environment than in the filled appstack.\n"
                   "'PUSH_ALL': deploy everything from filled appstack.'")
def deploy( #pylint: disable=too-many-arguments
        artifacts_location,
        cf_api_endpoint,
        cf_user,
        cf_password,
        cf_org,
        cf_space,
        fetcher_config,
        filled_appstack,
        expanded_appstack,
        appstack,
        push_strategy):
    """
    Deploy the whole appstack.
    This should be run from environment's bastion to reduce chance of errors.

    ARTIFACTS_LOCATION: Path to a directory with applications' artifacts (zips).
    It should be the "apps/" subdirectory of an unpacked TAP release package.

    CF_API_ENDPOINT: Endpoint of CF API. It should be the endpoint without auth-proxy, so it should
    probably look like this: "https://cf-api.<domain>".

    Example usage (deploying TAP from Apployer's directory within an unpacked TAP release package):

    apployer deploy ../apps https://cf-api.example.com -p <CF password>
    -e ../tools/expanded_appstack.yml
    """
    start_time = time.time()

    cf_info = CfInfo(api_url=cf_api_endpoint, password=cf_password, user=cf_user,
                     org=cf_org, space=cf_space)
    filled_appstack = _get_filled_appstack(appstack, expanded_appstack, filled_appstack,
                                           fetcher_config, artifacts_location)
    deploy_appstack(cf_info, filled_appstack, artifacts_location, push_strategy)

    _log.info('Deployment time: %s', _seconds_to_time(time.time() - start_time))


@cli.command()
@click.argument('ARTIFACTS_LOCATION')
@click.option('-f', '--fetch-conf', 'fetcher_config',
              default=DEFAULT_FETCHER_CONF, show_default=True,
              help='Path to the configuration file for environment configuration fetcher.')
@click.option('-e', '--expanded-appstack',
              default=DEFAULT_EXPANDED_APPSTACK_FILE,
              help="After expansion, expanded appstack will be saved in this location.")
@click.option('-a', '--appstack',
              default=DEFAULT_APPSTACK_FILE, show_default=True,
              help='Path to the file containing non-expanded appstack. Only used if expanded'
                   'appstack has not been specified.')
def fetch(artifacts_location, fetcher_config, expanded_appstack, appstack):
    """
    Fetch environment configuration, generate and fill expanded_appstack.yml file.
    This should be run from environment's bastion to reduce chance of errors.

    ARTIFACTS_LOCATION: Path to a directory with applications' artifacts (zips).
    It should be the "apps/" subdirectory of an unpacked TAP release package.

    Example usage (fetching environment configuration from Apployer's directory within
    an unpacked TAP release package):

    apployer fetch ../apps
    """
    if os.path.exists(appstack):
        expand_appstack(appstack, artifacts_location, expanded_appstack)
        final_appstack_path = fill_appstack(expanded_appstack, fetcher_config)
    else:
        raise ApployerArgumentError("Couldn't find any appstack file.")

    with open(final_appstack_path) as appstack_file:
        filled_appstack_dict = yaml.load(appstack_file)
        _log.info('Content of %s file: \n %s', final_appstack_path, yaml.dump(filled_appstack_dict))


def _get_filled_appstack( #pylint: disable=too-many-arguments
        appstack_path,
        expanded_appstack_path,
        filled_appstack_path,
        fetcher_config_path,
        artifacts_location):
    """ Does the necessary things to obtain a filled expanded appstack based on the command line
    parameters.

    Args:
        appstack_path (str): Path to appstack file.
        expanded_appstack_path (str): Path to expanded appstack file.
        filled_appstack_path (str): Path to filled expanded appstack file.
        fetcher_config_path (str): Path to the configuration file for environment configuration
            fetcher.
        artifacts_location (str): Path to a directory with applications' artifacts (zips).

    Returns:
        `AppStack`: Expanded appstack filled with configuration extracted from
            a live TAP environment.
    """
    if os.path.exists(filled_appstack_path):
        _log.info('Using filled expanded appstack file: %s', os.path.realpath(filled_appstack_path))
        final_appstack_path = filled_appstack_path
    elif os.path.exists(expanded_appstack_path):
        _log.info('Using expanded appstack file: %s', os.path.realpath(expanded_appstack_path))
        final_appstack_path = fill_appstack(expanded_appstack_path, fetcher_config_path)
    elif os.path.exists(appstack_path):
        _log.info('Using appstack file: %s', os.path.realpath(appstack_path))
        expand_appstack(appstack_path, artifacts_location, expanded_appstack_path)
        final_appstack_path = fill_appstack(expanded_appstack_path, fetcher_config_path)
    else:
        raise ApployerArgumentError("Couldn't find any appstack file.")

    with open(final_appstack_path) as appstack_file:
        filled_appstack_dict = yaml.load(appstack_file)
    return AppStack.from_appstack_dict(filled_appstack_dict)


def _setup_logging(level):
    log_formatter = logging.Formatter(
        '%(asctime)s-%(levelname)s-%(name)s: %(message)s',
        '%H:%M:%S')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(log_formatter)

    project_logger = logging.getLogger(apployer.__name__)
    project_logger.setLevel(level)
    project_logger.addHandler(handler)


class ApployerArgumentError(Exception):
    """Something isn't right with command line arguments."""
    pass


def _seconds_to_time(seconds):
    int_seconds = int(seconds)
    return '{}:{:02d}:{:02d}'.format(
        int_seconds // 3600,
        (int_seconds // 60) % 60,
        int_seconds % 60)


# TODO primary
# --dry-run (deployer functions should be in a class, some methods need to be overwritten,
#   need to check for existance first before trying to update/create services)
# make installable and testable for py26 (no networkx)
# Brokers serving instances that hold no data (like all WSSB brokers) can be marked as "recreatable"
#   or something. Then, they could be recreated and rebound to apps when WSSB configuration changes.
#   Right now it won't happen, because there's no universal way of recreating a service instance.
# add app timeout parameter (default should be 180 seconds), think about enxanced timeout and
#   differentiation between continuous crash and timeout
# make all docstrings conform to Google standard


# TODO secondary
# add retrying of CF CLI methods
# automatically download CF CLI
# Change "order" parameter in app configuration to "after" (a list). This way we can explicitly
#   define that some application needs to be created before the given one so it can work.
#   E.g. in hdfs-broker config: after: [auth-gateway]
#   Those dependencies can be resolved on the graph.
# Add a meaningful integration test and get rid of some unit tests with a lot of mocks.
# make creation of upsis and service instances parallel
#   (just use a ThreadPool for running them)
# document how to add a new application, broker, upsi, etc.
# switch all addresses to HTTPS
# add options for bastion addressess, users and key-files
