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
Appstack expansion - adding application manifests and sorting in deployment order.
"""

from contextlib import contextmanager
import itertools
import logging
import os
from os import path
import zipfile

import yaml

from .app_file import get_artifact_name
from .appstack import AppConfig, AppStack, MalformedAppStackError

# Code doing the deployment from a release package (already containing an expanded appstack)
# has to be compatible with Python 2.6 - networkx is not compatible with it but it won't have to
# be used.
try:
    import networkx
finally:
    pass

_log = logging.getLogger(__name__) # pylint: disable=invalid-name


def expand_appstack(appstack_file_path, artifacts_location, expanded_appstack_path):
    """Creates an expanded appstack, that is appstack with merged app manifests and also
    sorted in the order in which the applications should be deployed.

    Args:
        appstack_file_path (str): Location of appstack configuration file.
        artifacts_location (str): Location of deployable artifacts (zips) of platform applications.
        expanded_appstack_path (str): Where to store expanded appstack file.
    """
    with open(appstack_file_path) as appstack_file:
        appstack_dict = yaml.load(appstack_file)
        appstack = AppStack.from_appstack_dict(appstack_dict)
    manifests = _get_artifact_manifests(artifacts_location)

    _log.info('Expanding appstack with application manifests...')
    merged_appstack = appstack.merge_manifests(manifests)
    expanded_appstack = _sort_appstack(merged_appstack)

    with open(expanded_appstack_path, 'w') as expanded_appstack_file:
        _log.info('Saving expanded appstack file to %s', path.abspath(expanded_appstack_path))
        yaml.dump(
            expanded_appstack.to_dict(),
            expanded_appstack_file,
            default_flow_style=False,
            width=1000)


def _get_artifact_manifests(artifacts_path):
    """Gets application manifests from artifacts residing under the given path.
    All zip files will be interpreted as artifacts.

    Args:
        artifacts_path (str): Path to directory containing application artifacts.

    Returns:
        dict[str,dict]: Mapping of artifact name to manifest's fields,
            e.g. 'app_A': {'memory': '64M', 'command': './app_A'}
    """
    artifacts_path = path.abspath(artifacts_path)
    _log.info('Getting manifests from application zips in %s', artifacts_path)
    manifest_file_name = 'manifest.yml'
    manifests = {}
    zip_names = [name for name in os.listdir(artifacts_path) if name.endswith('.zip')]
    for zip_name in zip_names:
        zip_file = zipfile.ZipFile(path.join(artifacts_path, zip_name))
        if manifest_file_name not in zip_file.namelist():
            _log.debug("%s doesn't contain %s", zip_name, manifest_file_name)
            continue

        manifest_path = zip_file.extract(manifest_file_name)
        with open(manifest_path) as manifest_file:
            manifest_file_dict = yaml.load(manifest_file)
        os.remove(manifest_path)

        artifact_name = get_artifact_name(zip_name)
        _log.debug('Got manifest from artifact: %s', artifact_name)
        # Manifest file can theoretically contain more than one app definition, but our apps
        # have only themselves in their manifests.
        manifests[artifact_name] = manifest_file_dict['applications'][0]
    return manifests


def _sort_appstack(appstack): #pylint: disable=too-many-locals
    """
    Sorts the appstack so that applications and services can be successfully deployed going from
    first to last in "apps" and "user_provided_services" lists.
    :param `AppStack` appstack: The appstack to sort.
    :return: A new appstack with applications sorted in order they should be deployed.
    :rtype: `AppStack`
    """

    app_graph = networkx.DiGraph()
    service_providers = {}

    for app in appstack.apps:
        _log.debug('Adding app to dependency graph: %s', app.name)
        app_graph.add_node(app)
        # add exposed services to providers dictionary (service depends on app)
        for service in app.user_provided_services:
            _map_service_provider(service, app, service_providers)
        if app.broker_config:
            for service_instance in app.broker_config.service_instances:
                _map_service_provider(service_instance, app, service_providers)
        # add names of required services to graph (app depends on service)
        for service_name in app.app_properties.get('services', []):
            app_graph.add_edge(app, service_name)

    final_graph = _substitute_services(
        app_graph,
        service_providers,
        appstack.user_provided_services,
        appstack.brokers)
    _dump_graph(final_graph)
    _detect_cycles(final_graph)

    deployment_sequences = _get_app_deployment_sequences(final_graph)
    sorted_apps = list(itertools.chain(*deployment_sequences))
    final_sorted_apps = _apply_app_order_parameter(sorted_apps)

    sorted_appstack = appstack.copy()
    sorted_appstack.apps = final_sorted_apps
    return sorted_appstack


def _substitute_services(
        app_graph,
        service_providers,
        global_user_provided_services,
        global_brokers):
    """
    All edges in the graph are from an app to a service.
    This function creates a new graph in which apps are linked to the provider of the service
    they depend on (which is another application).
    :param `networkx.DiGraph` app_graph:
    :param dict[str,`AppConfig`] service_providers: Links service name and the application
        that provides it.
    :param list[dict] global_user_provided_services: List of standalone user provided services
        defined in the appstack.
    :param list[dict] global_brokers: List of brokers that aren't created from applications
        defined in appstack.
    :return: A new graph containing only links between applications.
    """
    global_broker_instances = itertools.chain(
        *[broker.service_instances for broker in global_brokers])
    global_broker_instances_names = [instance.name for instance in global_broker_instances]
    global_user_instances_names = [instance.name for instance in global_user_provided_services]
    global_instance_names = set(global_broker_instances_names + global_user_instances_names)
    final_graph = app_graph.copy()
    service_nodes = []

    for dependency in app_graph.edges():
        service_name = dependency[1]
        service_nodes.append(service_name)

        if service_name in service_providers:
            final_graph.add_edge(dependency[0], service_providers[service_name])
            _log.debug('Marked dependency of %s on %s through service %s.',
                       dependency[0].name, service_providers[service_name].name, service_name)
        elif service_name in global_instance_names:
            # We don't care about this edge since all global user provided services will
            # be created before first application is deployed.
            pass
        else:
            raise MalformedAppStackError("Service instance: " + service_name + " for: " +
                                         dependency[0].artifact_name + " isn't defined anywhere!")

    final_graph.remove_nodes_from(service_nodes)
    return final_graph


def _get_app_deployment_sequences(graph):
    """
    :param `networkx.DiGraph` graph:
    :return: Lists of applications that may be deployed in parallel.
    First list needs to be deployed first, the second one after that, etc.
    :rtype: list[list[`AppConfig`]]
    """
    deployment_sequences = []
    while graph:
        leaves = [component for component, dep_num in graph.out_degree_iter() if dep_num == 0]
        deployment_sequences.append(leaves)
        graph.remove_nodes_from(leaves)
    return deployment_sequences


def _map_service_provider(service_instance, app, service_providers):
    """
    Marks that a service is provided by an application.
    """
    service_name = service_instance.name
    if service_name not in service_providers:
        service_providers[service_name] = app
        _log.debug('Marking app %s as provider for service %s', app.name, service_name)
    else:
        raise MalformedAppStackError('The same service defined twice: ' + service_name)


def _detect_cycles(graph):
    """
    Detects cycles in graph and raises exception when it finds one.
    """
    cycles = list(networkx.algorithms.simple_cycles(graph))
    if cycles:
        with _simple_app_config_repr():
            raise MalformedAppStackError("Appstack can't be reliably deployed, because there "
                                         "are cycles in app dependencies: " + str(cycles))


def _dump_graph(graph):
    """
    Dumps the graph in GraphML format to a file.
    """
    dump_file = 'app_dependencies_graph.xml'
    _log.info("Dumping apps' dependencies graph to %s", path.realpath(dump_file))
    with _simple_app_config_repr():
        networkx.write_graphml(graph, dump_file)


@contextmanager
def _simple_app_config_repr():
    app_config_repr = AppConfig.__repr__
    try:
        AppConfig.__repr__ = lambda self: self.name
        yield
    finally:
        AppConfig.__repr__ = app_config_repr


def _apply_app_order_parameter(sorted_apps):
    """
    Args:
        sorted_apps (list[`AppConfig`]): List of applications in proper deployment order.

    Returns:
        list[`AppConfig`]: List changed to enforce "order" parameter in some applications.
    """
    ordered_apps_with_index = [(index, app) for index, app in enumerate(sorted_apps)
                               if app.is_ordered]
    app_orderings = [app.order for _, app in ordered_apps_with_index]
    if len(set(app_orderings)) < len(app_orderings):
        raise MalformedAppStackError('Few apps have the same order parameter!')

    final_apps = list(sorted_apps)
    ordered_apps = [app for _, app in ordered_apps_with_index]
    for app in ordered_apps:
        final_apps.remove(app)

    # We need to recalculate (normalize) negative orders.
    # They're no longer valid after changing size of final_apps by removing some apps.
    for app in ordered_apps:
        app.normalized_order = app.order + len(sorted_apps) if app.order < 0 else app.order

    # We need to have this sorted according to ascending "normalized_order" field.
    # Inserting application to in the list shifts all after it.
    sorted_ordered_apps = sorted(ordered_apps, key=lambda app: app.normalized_order)

    for app in sorted_ordered_apps:
        final_apps.insert(app.normalized_order, app)

    # Cleanup after order normalization
    for app in ordered_apps:
        del app.normalized_order

    return final_apps
