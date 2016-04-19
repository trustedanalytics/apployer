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
Representations of appstack and things contained within it.
"""

import copy
import logging

_log = logging.getLogger(__name__) # pylint: disable=invalid-name


class DataContainer(object):
    """
    Base class for data containers.
    """

    # Lambdas taking field/value pairs from __dict__ items.
    # If any field returns True for one of the filters then it's not included in the dictionary
    # being created in to_dict function.
    _to_dict_filters = []

    @classmethod
    def _obj_to_dict(cls, obj):
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        elif isinstance(obj, list):
            return [cls._obj_to_dict(element) for element in obj]
        else:
            return obj

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __repr__(self):
        """
        Helps investigating failing tests.
        """
        return '{}({})'.format(self.__class__.__name__, self.__dict__)

    def copy(self):
        """
        Returns:
            DataContainer: A deep copy of self.
        """
        return copy.deepcopy(self)

    def to_dict(self):
        """Used when converting the object to dictionary before serialization to YAML.

        Returns:
            dict: This object presented as a dictionary.
        """
        non_filtered = {field: self._obj_to_dict(value) for field, value in self.__dict__.items()}
        return {field: value for field, value in non_filtered.items()
                if value and
                not field.startswith('_') and
                value not in (None, [], {}) and
                not any([dict_filter(field, value) for dict_filter in self._to_dict_filters])}


class AppStack(DataContainer):
    """Representation of "appstack", that is the main configuration file of the platform containing
    applications, brokers and user-provided services that should appear on CloudFoundry.

    Attributes:
        apps (list[`AppConfig`]): List of applications composing the whole stack.
            The list shows in what order applications should be deployed,
            but only after using `expand` .
        user_provided_services (list[`UserProvidedService`]): Configuration of user provided
            service instances not created from any appstack application.
        brokers (list[`BrokerConfig`]): Configuration of brokers not created from any appstack
            application.
        buildpacks (list[str]): List of buildpacks (only their names) that need to be set up in CF.
        domain (str): Environment's address domain
            (e.g. for app.example.com, the domain is example.com).
    """

    def __init__(self, apps=None, user_provided_services=None, # pylint: disable=too-many-arguments
                 brokers=None, buildpacks=None, domain=None, security_groups=None):
        self.apps = apps or []
        self.user_provided_services = user_provided_services or []
        self.brokers = brokers or []
        self.buildpacks = buildpacks or []
        self.domain = domain or ''
        self.security_groups = security_groups or []

        self._validate_register_in()

    @staticmethod
    def from_appstack_dict(appstack):
        """
        Args:
            appstack (dict): Appstack YAML loaded into dictionary.

        Returns:
            `AppStack`: AppStack instance deserialized from a dictionary.
        """
        apps = AppStack._get_apps(appstack)
        user_provided_services = [UserProvidedService(**service_dict) for service_dict
                                  in appstack.get('user_provided_services', [])]
        brokers = [BrokerConfig.from_dict(broker_dict) for broker_dict
                   in appstack.get('brokers', [])]
        buildpacks = appstack.get('buildpacks', [])
        domain = appstack.get('domain')
        security_groups = [SecurityGroup.from_dict(sg_dict) for sg_dict
                           in appstack.get('security_groups', [])]
        return AppStack(apps, user_provided_services, brokers, buildpacks, domain, security_groups)

    @staticmethod
    def _get_apps(appstack):
        """
        Extracts application configurations from the appstack.
        :param dict appstack: Appstack YAML loaded into dictionary.
        :returns: A list of application configuration objects.
        :rtype: list[`AppConfig`]
        :raises `MalformedAppstackError`: When appstack configuration is invalid.
        """
        apps = []
        for app_dict in appstack.get('apps', []):
            try:
                app = AppConfig.from_dict(app_dict)
            except TypeError as ex:
                raise MalformedAppStackError('Application configuration malformed.\n'
                                             'Error: {}\n'
                                             'Application source dict: {}'.format(ex, app_dict))
            apps.append(app)
        return apps

    def merge_manifests(self, manifests):
        """
        Merges manifests of individual apps into appstack configuration, creating a new one.
        If there are conflicting values in manifests and appstack,
        the ones in appstack take precedence.
        :param dict manifests: Dictionary of dictionaries mapping app name to the rest
        of its parameters from manifest.yml.
        :return: Appstack with merged manifests.
        :rtype: `AppStack`
        """
        _log.info('Merging application manifests into appstack...')
        apps = []

        for app in self.apps:
            _log.debug('Merging manifest from artifact %s to %s application',
                       app.artifact_name, app.name)
            if app.artifact_name not in manifests:
                _log.debug("Artifact %s doesn't have a manifest.", app.artifact_name)
                manifests[app.artifact_name] = {}
            merged_app = app.merge_manifest(manifests[app.artifact_name])
            apps.append(merged_app)

        new_appstack = self.copy()
        new_appstack.apps = apps
        return new_appstack

    def _validate_register_in(self):
        """Checks if non-empty "register_in" fields in applications point to another application
        in appstack.

        Raises:
            MalformedAppStackError: When "register_in" field points to a nonexistent application.
        """
        registrator_apps = [app.register_in for app in self.apps if app.register_in]
        app_names = {app.name for app in self.apps}
        for registrator_app in registrator_apps:
            if registrator_app not in app_names:
                raise MalformedAppStackError('"register_in" field of some app points to a '
                                             'nonexistent app: {}'.format(registrator_app))


class MalformedAppStackError(Exception):
    """
    Appstack YAML was malformed.
    """
    pass


class AppConfig(DataContainer): # pylint: disable=too-many-instance-attributes
    """Configuration for a single application in appstack.

    Attributes:
        name (str): Name of under which the application will be deployed.
        app_properties (dict): Properties of the application taken from a Cloud Foundry manifest.
            Those are, for example, "services", "memory", "env", "name" (under which the app will be
            deployed.
        user_provided_services (list[`UserProvidedService`]): List of user provided services
            that should be created along with this application, e.g. a service providing the address
            of this application for other applications that want to use it.
        broker_config (`BrokerConfig`): Configuration for a broker that needs to be created
            from this app.
        artifact_name (str): Name of the application's artifact (project).
            If not set it will default to `name`.
        register_in (str): Name of other appstack application that this application needs to be
            registered in to achieve some special functionality.
        push_options (`PushOptions`): Parameters for pushing the app to Cloud Foundry.
        order (int): Fixed position in application's deployment sequence.
            If not provided it will be set automatically during application sorting.
        is_ordered (bool): Whether `order` is set to a meaningful value and should be taken into
            consideration.
        push_if: flag to determine if really create on environment
    """

    _to_dict_filters = [lambda key, _: key in ['is_ordered']]

    def __init__(self, name, app_properties=None,   # pylint: disable=too-many-arguments
                 user_provided_services=None, broker_config=None, artifact_name=None,
                 register_in=None, push_options=None, order=None, push_if=True):
        if not name:
            raise MalformedAppStackError("Application's name not specified.")
        self.name = name
        self.app_properties = app_properties or {}
        self.user_provided_services = user_provided_services or []
        self.broker_config = broker_config
        self.artifact_name = artifact_name or name
        self.register_in = register_in
        self.push_options = push_options or PushOptions()
        self.push_if = push_if

        self.order = order
        if isinstance(order, int):
            self.is_ordered = True
        elif order is None:
            self.is_ordered = False
        else:
            raise MalformedAppStackError('App {}: order parameter is not int.'.format(name))

    def __hash__(self):
        return hash('app' + self.name)

    @staticmethod
    def from_dict(app_config_dict):
        """
        Args:
            app_config_dict (dict): `AppConfig` instance serialized to a dictionary.

        Returns:
            `AppConfig`: Deserialized instance.
        """
        upsis = 'user_provided_services'
        push_options = 'push_options'
        broker_config = 'broker_config'
        init_dict = app_config_dict.copy()

        init_dict[upsis] = [UserProvidedService(**service_params)
                            for service_params in app_config_dict.get(upsis, [])]
        init_dict[push_options] = PushOptions(**app_config_dict.get(push_options, {}))
        if broker_config in app_config_dict:
            init_dict[broker_config] = BrokerConfig.from_dict(
                app_config_dict[broker_config])

        return AppConfig(**init_dict)

    def merge_manifest(self, app_manifest):
        """Merges the manifest of an application with it's properties defined in appstack.
        Values from appstack take precedence over the ones from manifest.
        If there's no 'name' in app_properties then it will be filled self.name.

        Args:
            app_manifest(dict): Properties of the application (e.g. "name", "env", "services",
                "memory") taken from it's "manifest.yml".

        Returns:
            `AppConfig`: Application's config expanded by its manifest.
        """
        merged_config = copy.deepcopy(self)
        merged_app_properties = merged_config.app_properties

        for key, value in app_manifest.items():
            # TODO if value in manifest has different type than in config raise an error
            if isinstance(value, dict):
                merged_dict = value.copy()
                appstack_value = merged_app_properties.get(key, {})
                merged_dict.update(appstack_value)
                merged_app_properties[key] = merged_dict
            elif isinstance(value, list):
                merged_list = value + merged_app_properties.get(key, [])
                merged_app_properties[key] = list(set(merged_list))
            elif key not in merged_app_properties:
                merged_app_properties[key] = value

        if 'name' not in merged_app_properties:
            merged_app_properties['name'] = self.name

        return merged_config

    # TODO add a function that expands the config with default CF parameters
    # those will only affect app_properties


class PushOptions(DataContainer):
    """Options for pushing the application to Cloud Foundry

    Attributes:
        params (str): String with other parameters for "cf push" command.
        post_command (str): Shell command that will be run after pushing the application.
    """

    def __init__(self, params='', post_command=None):
        self.params = params
        self.post_command = post_command


class BrokerConfig(DataContainer):
    """Configuration of a Cloud Foundry service broker.

    Attributes:
        name (str): Broker's name visible in marketplace.
        url (str): URL under which the broker is available.
        auth_username (str): Broker's username/
        auth_password (str): Broker's password.
        service_instances (list[`ServiceInstance`]): Instances that will be created from this
            broker.
        push_if: flag to determine if really create on environment
    """

    def __init__(self, name, url, auth_username, auth_password, # pylint: disable=too-many-arguments
                 services=None, service_instances=None, push_if=True):
        # TODO validate the fields
        self.name = name
        self.url = url
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.services = services or []
        self.service_instances = service_instances or []
        self.push_if = push_if

    @staticmethod
    def from_dict(broker_config_dict):
        """
        Args:
            broker_config_dict (dict): `BrokerConfig` instance serialized to a dictionary.

        Returns:
            `BrokerConfig`: Deserialized instance.
        """
        service_instances = 'service_instances'
        init_dict = broker_config_dict.copy()

        init_dict[service_instances] = [
            ServiceInstance(**service_params)
            for service_params in broker_config_dict.get(service_instances, [])]
        return BrokerConfig(**init_dict)


class ServiceInstance(DataContainer):
    """Configuration of a Cloud Foundry service instance created from a broker.

    Attributes:
        name (str): Name of the service instance.
        plan (str): Broker plan for which the service will be created.
        label (str): Additional description for creating services with special brokers, e.g. Docker
            broker.
        push_if: flag to determine if really create on environment
    """

    def __init__(self, name, plan, label=None, push_if=True):
        # TODO validate the fields
        self.name = name
        self.plan = plan
        self.label = label
        self.push_if = push_if


class UserProvidedService(DataContainer):
    """Configuration of a Cloud Foundry user-provided service instance.

    Attributes:
        name (str): Instance's name.
        credentials (dict): Service's credentials - the content that get into application's
            environment when binding the service.
        push_if: flag to determine if really create on environment
    """

    def __init__(self, name, credentials, push_if=True):
        # TODO validate the fields
        self.name = name
        self.credentials = credentials
        self.push_if = push_if


class SecurityGroup(DataContainer):
    """Configuration of a Cloud Foundry security group.

    Attributes:
        name (str): Instance's name.
        protocol (str): Service's credentials - the content that get into application's
        environment when binding the service.
        destination (str): Same as in CF (refer to cf help)
        ports (str): Same as in CF (refer to cf help)
        push_if: flag to determine if really create on environment
    """
    #pylint: disable=too-many-arguments
    def __init__(self, name, protocol, destination, ports, push_if=True):
        self.name = name
        self.protocol = protocol
        self.destination = destination
        self.ports = ports
        self.push_if = push_if

    @classmethod
    def from_dict(cls, security_group_dict):
        """
        Args:
            security_group_dict (dict): `SecurityGroup` instance serialized to a dictionary.

        Returns:
        `SecurityGroup`: Deserialized instance.
        """
        name = security_group_dict['name']
        protocol = security_group_dict['protocol']
        destination = security_group_dict['destination']
        ports = security_group_dict['ports']
        push_if = security_group_dict['push_if']

        return cls(name, protocol, destination, ports, push_if)

    def to_dict_for_cf_json(self):
        """Creates dict from instance of this class for CF create-security-group json (i.e.
        without name and push_if)"""
        security_group_dict = dict()
        security_group_dict['protocol'] = self.protocol
        security_group_dict['destination'] = self.destination
        security_group_dict['ports'] = self.ports

        return security_group_dict
