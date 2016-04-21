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

# TODO refactor the file and turn on pylint
#pylint: skip-file

import base64
import json
import logging
import os
import tempfile

try:
    from sshtunnel import SSHTunnelForwarder
except ImportError:
    from sshtunnel.sshtunnel import SSHTunnelForwarder

from cm_api.api_client import ApiResource
import paramiko
import yaml
import requests
import xml.etree.ElementTree as ET

GENERATE_KEYTAB_SCRIPT = """#!/bin/sh

function tmp_file () {
    TFILE="/tmp/$(basename $0).$$.keytab"
echo $TFILE
}

TMP=$(tmp_file)
CMD=$(
    {
        PRINC=$@
echo "xst -norandkey -k $TMP $PRINC"
})
sudo kadmin.local -q "$CMD" 2&> /dev/null
sudo base64 $TMP
sudo rm $TMP
"""


class CdhConfExtractor(object):
    def __init__(self, config):
        self._logger = logging.getLogger(__name__)
        self._hostname = config['machines']['cdh-launcher']['hostname']
        self._hostport = config['machines']['cdh-launcher']['hostport']
        self._username = config['machines']['cdh-launcher']['username']
        key_path = config['machines']['cdh-launcher']['key_filename']
        self._key = os.path.expanduser(key_path)
        self._key_password = config['machines']['cdh-launcher']['key_password']
        self._is_openstack = config['openstack_env']
        self._is_kerberos = config['kerberos_used']
        self._cdh_manager_ip = config['machines']['cdh-manager']['ip']
        self._cdh_manager_user = config['machines']['cdh-manager']['user']
        self._cdh_manager_sshtunnel_required = config['machines']['cdh-manager']['sshtunnel_required']
        self._cdh_manager_password = config['machines']['cdh-manager']['password']

    def __enter__(self):
        extractor = self
        try:
            if self._cdh_manager_sshtunnel_required:
                self._logger.info('Creating tunnel to CDH-Manager.')
                extractor.create_tunnel_to_cdh_manager()
                extractor.start_cdh_manager_tunneling()
                self._logger.info('Tunnel to CDH-Manager has been created.')
            else:
                self._logger.info('Connection to CDH-Manager host without ssh tunnel.')
                self._local_bind_address = self.extract_cdh_manager_host()
                self._local_bind_port = 7180
            return extractor
        except Exception as exc:
            self._logger.error('Cannot creating tunnel to CDH-Manager machine.')
            raise exc

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._cdh_manager_sshtunnel_required:
                self.stop_cdh_manager_tunneling()
                self._logger.info('Tunelling to CDH-Manager stopped.')
        except Exception as exc:
            self._logger.error('Cannot close tunnel to CDH-Manager machine.')
            raise exc

    # Cdh launcher methods
    def create_ssh_connection(self, hostname, username, key_filename, key_password):
        try:
            self._logger.info('Creating connection to remote host {0}.'.format(hostname))
            self.ssh_connection = paramiko.SSHClient()
            self.ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_connection.connect(hostname, username=username, key_filename=key_filename, password=key_password)
            self._logger.info('Connection to host {0} established.'.format(hostname))
        except Exception as exc:
            self._logger.error('Cannot creating connection to host {0} machine. Check your settings '
                               'in fetcher_config.yml file.'.format(hostname))
            raise exc

    def close_ssh_connection(self):
        try:
            self.ssh_connection.close()
            self._logger.info('Connection to remote host closed.')
        except Exception as exc:
            self._logger.error('Cannot close connection to the remote host.')
            raise exc

    def ssh_call_command(self, command, subcommands=None):
        self._logger.info('Calling remote command: "{0}" with subcommands "{1}"'.format(command, subcommands))
        ssh_in, ssh_out, ssh_err = self.ssh_connection.exec_command(command, get_pty=True)
        if subcommands != None:
            for subcommand in subcommands:
                ssh_in.write(subcommand + '\n')
                ssh_in.flush()
        return ssh_out.read() if ssh_out is not None else ssh_err.read()

    def extract_cdh_manager_host(self):
        self._logger.info('Extracting CDH-Manager address.')
        if self._cdh_manager_ip is None:
            self.create_ssh_connection(self._hostname, self._username, self._key, self._key_password)
            if self._is_openstack:
                ansible_ini = self.ssh_call_command('cat ansible-cdh/platform-ansible/inventory/cdh')
            else:
                ansible_ini = self.ssh_call_command('cat ansible-cdh/inventory/cdh')
            self._cdh_manager_ip = self._get_host_ip('cdh-manager', ansible_ini)
            self.close_ssh_connection()
        self._logger.info('CDH-Manager adress extracted: {}'.format(self._cdh_manager_ip))
        return self._cdh_manager_ip

    # Cdh manager methods
    def create_tunnel_to_cdh_manager(self, local_bind_address='localhost', local_bind_port=7180, remote_bind_port=7180):
        self._local_bind_address = local_bind_address
        self._local_bind_port = local_bind_port
        self.cdh_manager_tunnel = SSHTunnelForwarder(
            (self._hostname, self._hostport),
            ssh_username=self._username,
            local_bind_address=(local_bind_address, local_bind_port),
            remote_bind_address=(self.extract_cdh_manager_host(), remote_bind_port),
            ssh_private_key_password=self._key_password,
            ssh_private_key=self._key
        )

    def start_cdh_manager_tunneling(self):
        try:
            self.cdh_manager_tunnel.start()
        except Exception as e:
            self._logger.error('Cannot start tunnel: ' + e.message)

    def stop_cdh_manager_tunneling(self):
        try:
            self.cdh_manager_tunnel.stop()
        except Exception as e:
            self._logger.error('Cannot stop tunnel: ' + e.message)

    def extract_cdh_manager_details(self, settings):
        for host in settings['hosts']:
            if 'cdh-manager' in host['hostname']:
                return host

    def extract_nodes_info(self, name, settings):
        nodes = []
        for host in settings['hosts']:
            if name in host['hostname']:
                nodes.append(host)
        return nodes

    def extract_service_namenode(self, service_name, role_name, settings):
        hdfs_service = self._find_item_by_attr_value(service_name, 'name', settings['clusters'][0]['services'])
        hdfs_namenode = self._find_item_by_attr_value(role_name, 'name', hdfs_service['roles'])
        host_id = hdfs_namenode['hostRef']['hostId']
        return self._find_item_by_attr_value(host_id, 'hostId', settings['hosts'])['hostname']

    def get_client_config_for_service(self, service_name):
        result = requests.get('http://{0}:{1}/api/v10/clusters/CDH-cluster/services/{2}/clientConfig'.format(self._local_bind_address, self._local_bind_port, service_name))
        return base64.standard_b64encode(result.content)

    def generate_keytab(self, principal_name):
        def transfer_keytab_script(target):
            sftp = self.ssh_connection.open_sftp()
            with tempfile.NamedTemporaryFile('w') as f:
                f.file.write(GENERATE_KEYTAB_SCRIPT)
                f.file.close()
                sftp.put(f.name, target)
        self._logger.info('Generating keytab for {} principal.'.format(principal_name))
        self.create_ssh_connection(self._hostname, self._username, self._key, self._key_password)

        transfer_keytab_script('/tmp/generate_keytab_script.sh')

        self.ssh_call_command('scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no /tmp/generate_keytab_script.sh {0}:/tmp/'.format(self._cdh_manager_ip))
        self.ssh_call_command('ssh -t {0} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "chmod 700 /tmp/generate_keytab_script.sh"'.format(self._cdh_manager_ip))
        keytab_hash = self.ssh_call_command('ssh -t {0} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "/tmp/generate_keytab_script.sh {1}"'
                                            .format(self._cdh_manager_ip, principal_name))
        self.close_ssh_connection()
        lines = keytab_hash.splitlines()
        self._logger.info('Keytab for {} principal has been generated.'.format(principal_name))
        return '{}'.format(''.join(lines[2:-2]))

    def generate_base64_for_file(self, file_path, hostname):
        self._logger.info('Generating base64 for {} file.'.format(file_path))
        self.create_ssh_connection(self._hostname, self._username, self._key, self._key_password)
        base64_file_hash = self.ssh_call_command('ssh -t {0} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "base64 {1}"'.format(hostname, file_path))
        self.close_ssh_connection()
        lines = base64_file_hash.splitlines()
        self._logger.info('Base64 hash for {0} file on {1} machine has been generated.'.format(file_path, hostname))
        return '{}'.format(''.join(lines[2:-2]))

    def get_all_deployments_conf(self):
        result = {}
        deployments_settings = json.loads(requests.get('http://' + self._local_bind_address + ':'
                                                       + str(self._local_bind_port) + '/api/v10/cm/deployment',
                                                    auth=(self._cdh_manager_user, self._cdh_manager_password)).content)
        result['cloudera_manager_internal_host'] = self.extract_cdh_manager_details(deployments_settings)['hostname']

        helper = CdhApiHelper(ApiResource(self._local_bind_address, username=self._cdh_manager_user, password=self._cdh_manager_password, version=9))
        if self._is_kerberos:
            result['kerberos_host'] = result['cloudera_manager_internal_host']
            result['hdfs_keytab_value'] = self.generate_keytab('hdfs')
            result['auth_gateway_keytab_value'] = self.generate_keytab('authgateway/sys')
            result['hgm_keytab_value'] = self.generate_keytab('hgm/sys')
            result['vcap_keytab_value'] = self.generate_keytab('vcap')
            result['krb5_base64'] = self.generate_base64_for_file('/etc/krb5.conf', self._cdh_manager_ip)
            result['kerberos_cacert'] = self.generate_base64_for_file('/var/krb5kdc/cacert.pem', self._cdh_manager_ip)

            sentry_service = helper.get_service_from_cdh('SENTRY')
            result['sentry_port'] = helper.get_entry(sentry_service, 'sentry_service_server_rpc_port')
            result['sentry_address'] = helper.get_host(sentry_service)
            result['sentry_keytab_value'] = self.generate_keytab('hive/sys')
            result['auth_gateway_profile'] = 'cloud,sentry-auth-gateway,zookeeper-auth-gateway,hdfs-auth-gateway,kerberos-hgm-auth-gateway,yarn-auth-gateway,hbase-auth-gateway'
            hgm_service = helper.get_service_from_cdh('HADOOPGROUPSMAPPING')
            result['hgm_adress'] = 'http://' + helper.get_host(hgm_service, 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER') + ':' \
                                   + helper.get_entry_from_group(hgm_service, 'rest_port', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')
            result['hgm_password'] = helper.get_entry_from_group(hgm_service, 'basic_auth_pass', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')
            result['hgm_username'] = helper.get_entry_from_group(hgm_service, 'basic_auth_user', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')
        else:
            result['sentry_port'] = ''
            result['sentry_address'] = ''
            result['sentry_keytab_value'] = ''
            result['hdfs_keytab_value'] = ''
            result['auth_gateway_keytab_value'] = ''
            result['vcap_keytab_value'] = ''
            result['hgm_keytab_value'] = ''
            result['krb5_base64'] = ''
            result['kerberos_cacert'] = ''
            result['auth_gateway_profile'] = 'cloud,zookeeper-auth-gateway,hdfs-auth-gateway,https-hgm-auth-gateway,yarn-auth-gateway,hbase-auth-gateway'
            hgm_service = helper.get_service_from_cdh('HADOOPGROUPSMAPPING')
            result['hgm_adress'] = 'https://' + helper.get_host(hgm_service, 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER') + ':'\
                                   + helper.get_entry_from_group(hgm_service, 'rest_port', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')
            result['hgm_password'] = helper.get_entry_from_group(hgm_service, 'basic_auth_pass', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')
            result['hgm_username'] = helper.get_entry_from_group(hgm_service, 'basic_auth_user', 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER-BASE')

        result['cloudera_address'] = result['cloudera_manager_internal_host']
        result['cloudera_port'] = 7180
        result['cloudera_user'] = self._cdh_manager_user
        result['cloudera_password'] = self._cdh_manager_password

        oozie_server = helper.get_service_from_cdh('OOZIE')
        result['oozie_server'] = 'http://' + helper.get_host(oozie_server) + ':' + helper.get_entry(oozie_server, 'oozie_http_port')

        yarn = helper.get_service_from_cdh('YARN')
        result['job_tracker'] = helper.get_host(yarn) + ':' + helper.get_entry(yarn, 'yarn_resourcemanager_address')

        sqoop_client = helper.get_service_from_cdh('SQOOP_CLIENT')
        result['metastore'] = self._get_property_value(helper.get_entry(sqoop_client, 'sqoop-conf/sqoop-site.xml_client_config_safety_valve'), 'sqoop.metastore.client.autoconnect.url')

        master_nodes = self.extract_nodes_info('cdh-master', deployments_settings)
        for i, node in enumerate(master_nodes):
            result['master_node_host_' + str(i+1)] = node['hostname']
        result['namenode_internal_host'] = self.extract_service_namenode('HDFS', 'HDFS-NAMENODE', deployments_settings)
        result['hue_node'] = self.extract_service_namenode('HUE', 'HUE-HUE_SERVER', deployments_settings)
        result['h2o_node'] = self.extract_nodes_info('cdh-worker-0', deployments_settings)[0]['hostname']
        result['arcadia_node'] = self.extract_nodes_info('cdh-worker-0', deployments_settings)[0]['hostname']
        result['import_hadoop_conf_hdfs'] = self.get_client_config_for_service('HDFS')
        result['import_hadoop_conf_hbase'] = self.get_client_config_for_service('HBASE')
        result['import_hadoop_conf_yarn'] = self.get_client_config_for_service('YARN')
        result['import_hadoop_conf_hive'] = self.get_client_config_for_service('HIVE')

        return result

    # helpful methods

    def _get_property_value(self, config, key):
        properties = ET.fromstring('<properties>' + config + '</properties>')
        for property in properties:
            if property.find('name').text == key:
                return property.find('value').text

    def _find_item_by_attr_value(self, attr_value, attr_name, array_with_dicts):
        return next(item for item in array_with_dicts if item[attr_name] == attr_value)

    def _get_host_ip(self, host, ansible_ini):
        host_info = []
        for line in ansible_ini.split('\n'):
            if host in line:
                host_info.append(line.strip())
        return host_info[host_info.index('[' + host + ']') + 1].split(' ')[1].split('=')[1]

    def _load_config_yaml(self, filename):
        with open(filename, 'r') as stream:
            return yaml.load(stream)


class CdhApiHelper(object):

    def __init__(self, cdhApi):
        self.cdhApi = cdhApi

    def get_service_from_cdh(self, name):
        cluster = self.cdhApi.get_all_clusters()[0]
        try:
            return next(service for service in cluster.get_all_services() if service.type == name)
        except StopIteration:
            raise NoCdhServiceError('No {} in CDH services.'.format(name))

    # get host ip for service or specified service role
    def get_host(self, service, role = None):
        if role is None:
            id = service.get_all_roles()[0].hostRef.hostId
        else:
            id = service.get_role(role).hostRef.hostId
        return self.cdhApi.get_host(id).hostname

    def get_entry(self, service, name):
        sentry_config = service.get_all_roles()[0].get_config('full')
        for config_entry in sentry_config:
            if name == config_entry:
                entry = sentry_config[config_entry].value or sentry_config[config_entry].default
        return entry

    def get_entry_from_group(self, service, name, group):
        sentry_config = service.get_role_config_group(group).get_config('full')
        for config_entry in sentry_config:
            if name == config_entry:
                entry = sentry_config[config_entry].value or sentry_config[config_entry].default
        return entry


class NoCdhServiceError(Exception):
    pass

