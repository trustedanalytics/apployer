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
# pylint: skip-file

import re
import json
import yaml
import logging
import tempfile
import paramiko
import subprocess
import shutil
import urlparse
import xml.etree.ElementTree as ET
import ConfigParser

from .expressions import ExpressionsEngine, FsKeyValueStore, return_fixed_output

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

PORT_CHECKER_SCRIPT = """
import socket;
import sys;
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(("{hostname}", {port}))
print(result);
"""

hgm_service_name = 'HADOOPGROUPSMAPPING'
hgm_role_name = 'HADOOPGROUPSMAPPING-HADOOPGROUPSMAPPING_RESTSERVER'

DEFAULT_SENTRY_PORT = 8038
DEFAULT_ARCADIA_PORT = 80
DEFAULT_HUE_PORT = 8888
DEFAULT_OOZIE_PORT = '11000'
DEFAULT_YARN_PORT = '8032'


class ConfigurationExtractor(object):
    def __init__(self, config):
        self._logger = logging.getLogger(__name__)
        self._hostname = config['jumpbox']['hostname']
        self._ssh_required = False if self._hostname == 'localhost' else True
        self._ssh_connection = None
        self._hostport = config['jumpbox']['hostport']
        self._username = config['jumpbox']['username']
        self._ssh_key_filename = config['jumpbox']['key_filename']
        self._ssh_key_password = config['jumpbox']['key_password']
        self._kerberos_used = config['kerberos_used']
        self._kubernetes_used = config['kubernetes_used']
        self._paths = config['paths']
        self._cdh_manager_user = config['cdh-manager']['user']
        self._cdh_manager_password = config['cdh-manager']['password']
        self._cdh_manager_port = config['cdh-manager']['cm_port']
        self._cdh_manager_ssh_user = config['cdh-manager']['ssh_user']
        self._inventory = self._generate_inventory(config['workers_count'], config['masters_count'], config['envname'])
        self._envname = config['envname']

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    # Cdh launcher methods
    def _create_ssh_connection(self):
        try:
            self._logger.info('Creating connection to JUMPBOX %s.', self._hostname)
            self._ssh_connection = paramiko.SSHClient()
            self._ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_connection.connect(self._hostname, username=self._username,
                                         key_filename=self._ssh_key_filename, password=self._ssh_key_password)
            self._logger.info('Connection to JUMPBOX %s established.', self._hostname)
        except Exception as exc:
            self._logger.error(
                'Cannot create connection to JUMPBOX host. Check your settings in fetcher_config.yml file.')
            raise exc

    def _close_ssh_connection(self):
        try:
            self._ssh_connection.close()
            self._logger.info('Connection to JUMPBOX has been closed.')
        except Exception as exc:
            self._logger.error('Cannot close connection to the JUMPBOX.')
            raise exc

    def evaluate_expressions(self, deployment_variables):
        self._logger.info('Evaluating expressions from deployment variables')
        if self._ssh_required:
            self._create_ssh_connection()

        passwords_store = FsKeyValueStore(self._paths['passwords_store'], self._ssh_required,
                                          self._ssh_connection or None)
        self._exppressions_engine = ExpressionsEngine(passwords_store)
        for key, value in deployment_variables.iteritems():
            deployment_variables[key] = self._exppressions_engine.parse_and_apply_expression(key, value)

        if self._ssh_required:
                self._close_ssh_connection()

        self._logger.info('Expressions evaluated')
        return deployment_variables

    def get_deployment_configuration(self):
        self._logger.info('Getting deployment configuration')
        if self._ssh_required:
            self._create_ssh_connection()
        self._jumpboxes_vars = self._get_ansible_hosts()
        docker_yml_data = self._get_data_from_cf_tiny_yaml()
        cdh_manager_data = self._get_data_from_cdh_manager()
        if self._ssh_required:
            self._close_ssh_connection()
        self._logger.info('Deployment configuration downloaded')
        return dict(docker_yml_data.items() + cdh_manager_data.items())

    def _get_ansible_hosts(self):
        inventory_file_content = return_fixed_output(
            self._execute_command('sudo -i cat ' + self._paths['ansible_hosts']), rstrip=False)
        with tempfile.NamedTemporaryFile('w') as f:
            f.file.write(inventory_file_content)
            f.file.close()
            config = ConfigParser.RawConfigParser(allow_no_value=True)
            config.readfp(open(f.name))
            return config

    def _get_ansible_var(self, option, section='jump-boxes:vars', default_value=''):
        if self._jumpboxes_vars.has_option(section, option):
            return self._jumpboxes_vars.get(section, option)
        else:
            return default_value

    def _get_data_from_cf_tiny_yaml(self):
        cf_tiny_yaml_file_content = self._execute_command('sudo -i cat ' + self._paths['cf_tiny_yml'])
        cf_tiny_yaml_file_content = return_fixed_output(cf_tiny_yaml_file_content, rstrip=False)
        cf_tiny_yaml = yaml.load(cf_tiny_yaml_file_content)
        result = {
            "nats_ip": cf_tiny_yaml['properties']['nats']['machines'][0],
            "cf_admin_password": cf_tiny_yaml['properties']['loggregator_endpoint']['shared_secret'],
            "cf_admin_client_password": cf_tiny_yaml['properties']['loggregator_endpoint']['shared_secret'],
            "apps_domain": cf_tiny_yaml['properties']['domain'],
            "tap_console_password": cf_tiny_yaml['properties']['loggregator_endpoint']['shared_secret'],
            "atk_client_pass": cf_tiny_yaml['properties']['loggregator_endpoint']['shared_secret'],
            "email_address": cf_tiny_yaml['properties']['login']['smtp']['senderEmail'],
            "run_domain": cf_tiny_yaml['properties']['domain'],
            "smtp_pass": '"{}"'.format(cf_tiny_yaml['properties']['login']['smtp']['password']),
            "smtp_user": '"{}"'.format(cf_tiny_yaml['properties']['login']['smtp']['user']),
            "smtp_port": cf_tiny_yaml['properties']['login']['smtp']['port'],
            "smtp_host": cf_tiny_yaml['properties']['login']['smtp']['host'],
            "smtp_protocol": self._determine_smtp_protocol(cf_tiny_yaml['properties']['login']['smtp']['port']),
            "cloudera_manager_internal_host": self._inventory['cdh-manager'][0]
        }
        for i, node in enumerate(self._inventory['cdh-master']):
            result['master_node_host_{}'.format(i + 1)] = node
        return result

    def _get_data_from_cdh_manager(self):
        self._cdh_manager_hostname = self._inventory['cdh-manager'][0]
        deployments_settings_endpoint = 'http://{}:{}/api/v10/cm/deployment'.format(self._cdh_manager_hostname,
                                                                                    self._cdh_manager_port)
        self._logger.info('Send request to %s', deployments_settings_endpoint)
        response = self._execute_command('curl -X GET {} -u {}:{}'
                                         .format(deployments_settings_endpoint, self._cdh_manager_user,
                                                 self._cdh_manager_password))
        deployment_settings = json.loads(response)
        result = dict()

        result['sentry_port'] = ''
        result['sentry_address'] = ''
        result['sentry_keytab_value'] = ''
        result['hdfs_keytab_value'] = ''
        result['auth_gateway_keytab_value'] = ''
        result['vcap_keytab_value'] = ''
        result['hgm_keytab_value'] = ''
        result['krb5_base64'] = ''
        result['kerberos_cacert'] = ''
        result['auth_gateway_profile'] = 'cloud,warehouse-auth-gateway,zookeeper-auth-gateway,hdfs-auth-gateway,' \
                                         'https-hgm-auth-gateway,yarn-auth-gateway,hbase-auth-gateway'
        if self._kerberos_used:
            result['kerberos_host'] = self._cdh_manager_hostname
            result['hdfs_keytab_value'] = self._generate_keytab('hdfs')
            result['auth_gateway_keytab_value'] = self._generate_keytab('authgateway/sys')
            result['hgm_keytab_value'] = self._generate_keytab('hgm/sys')
            result['vcap_keytab_value'] = self._generate_keytab('vcap')
            result['krb5_base64'] = self._generate_base64_for_file('/etc/krb5.conf')
            result['kerberos_cacert'] = self._generate_base64_for_file('/var/krb5kdc/cacert.pem')
            sentry_service = self._find_item_by_attr_value('SENTRY', 'name',
                                                           deployment_settings['clusters'][0]['services'])
            result['sentry_port'] = self._find_item_by_attr_value('sentry_service_server_rpc_port', 'name',
                                                                  sentry_service['config']['items']).get('value') \
                                    or DEFAULT_SENTRY_PORT
            result['sentry_address'] = self._get_host('SENTRY', 'SENTRY-SENTRY_SERVER', deployment_settings).get(
                'hostname')
            result['sentry_keytab_value'] = self._generate_keytab('hive/sys')
            result[
                'auth_gateway_profile'] = 'cloud,kerberos-warehouse-auth-gateway,zookeeper-auth-gateway,hdfs-auth-gateway,' \
                                          'kerberos-hgm-auth-gateway,yarn-auth-gateway,hbase-auth-gateway'

        result['vpc'] = ''
        result['region'] = ''
        result['kubernetes_aws_access_key_id'] = ''
        result['kubernetes_aws_secret_access_key'] = ''
        result['key_name'] = ''
        result['consul_dc'] = ''
        result['consul_join'] = ''
        result['kubernetes_subnet_cidr'] = ''
        result['kubernetes_subnet'] = ''
        result['quay_io_username'] = ''
        result['quay_io_password'] = ''
        if self._get_ansible_var('provider') == 'aws' and self._kubernetes_used:
            result['vpc'] = self._get_vpc_id()
            result['region'] = self._get_ansible_var('region')
            result['kubernetes_aws_access_key_id'] = self._get_ansible_var('kubernetes_aws_access_key_id')
            result['kubernetes_aws_secret_access_key'] = self._get_ansible_var('kubernetes_aws_secret_access_key')
            result['key_name'] = self._get_ansible_var('key_name')
            result['consul_dc'] = self._envname
            result['consul_join'] = return_fixed_output(self._execute_command('host cdh-master-0')).split()[3]
            result['kubernetes_subnet'] = self._get_ansible_var('kubernetes_subnet_id')

            command_output = self._execute_command(
                'aws --region {} ec2 describe-subnets --filters Name=subnet-id,Values={}'
                    .format(result['region'], result['kubernetes_subnet']))
            subnet_json = json.loads(return_fixed_output(command_output, rstrip=False))
            result['kubernetes_subnet_cidr'] = subnet_json['Subnets'][0]['CidrBlock']
            result['quay_io_username'] = self._get_ansible_var('quay_io_username')
            result['quay_io_password'] = self._get_ansible_var('quay_io_password')

        result['java_http_proxy'] = ''
        if self._get_ansible_var('provider') == 'openstack':
            result['java_http_proxy'] = self._get_java_http_proxy()

        result['kubernetes_used'] = self._kubernetes_used

        hgm_service = self._find_item_by_attr_value(hgm_service_name, 'name',
                                                    deployment_settings['clusters'][0]['services'])
        hgm_protocol = 'http://' if self._kerberos_used else 'https://'
        result['hgm_adress'] = hgm_protocol + self._get_host(hgm_service_name, hgm_role_name, deployment_settings)[
            'hostname'] + ':' + self._find_item_by_attr_value('rest_port', 'name',
                                                              self._find_item_by_attr_value(hgm_role_name + '-BASE',
                                                                                            'name', hgm_service[
                                                                                                'roleConfigGroups'])[
                                                                  'config']['items'])['value']
        result['hgm_password'] = self._find_item_by_attr_value('basic_auth_pass', 'name',
                                                               self._find_item_by_attr_value(hgm_role_name + '-BASE',
                                                                                             'name', hgm_service[
                                                                                                 'roleConfigGroups'])[
                                                                   'config']['items'])['value']
        result['hgm_username'] = self._find_item_by_attr_value('basic_auth_user', 'name',
                                                               self._find_item_by_attr_value(hgm_role_name + '-BASE',
                                                                                             'name', hgm_service[
                                                                                                 'roleConfigGroups'])[
                                                                   'config']['items'])['value']

        result['oozie_server'] = 'http://' + self._get_host('OOZIE', 'OOZIE-OOZIE_SERVER', deployment_settings)[
            'hostname'] + ':' + DEFAULT_OOZIE_PORT

        result['job_tracker'] = self._get_host('YARN', 'YARN-GATEWAY', deployment_settings)[
                                    'hostname'] + ':' + DEFAULT_YARN_PORT

        sqoop_client = self._find_item_by_attr_value('SQOOP_CLIENT', 'name',
                                                     deployment_settings['clusters'][0]['services'])
        sqoop_entry = self._find_item_by_attr_value('sqoop-conf/sqoop-site.xml_client_config_safety_valve', 'name',
                                                    self._find_item_by_attr_value('SQOOP_CLIENT-GATEWAY-BASE', 'name',
                                                                                  sqoop_client['roleConfigGroups'])[
                                                        'config']['items'])['value']
        result['metastore'] = self._get_property_value(sqoop_entry, 'sqoop.metastore.client.autoconnect.url')

        result['cloudera_address'] = self._inventory['cdh-manager'][0]
        result['cloudera_port'] = self._cdh_manager_port
        result['cloudera_user'] = self._cdh_manager_user
        result['cloudera_password'] = self._cdh_manager_password

        result['namenode_internal_host'] = self._get_host('HDFS', 'HDFS-NAMENODE', deployment_settings)['hostname']
        result['hue_node'] = self._get_host('HUE', 'HUE-HUE_SERVER', deployment_settings)['hostname']
        result['hue_port'] = DEFAULT_HUE_PORT
        result['external_tool_hue'] = self._check_port(result['hue_node'], result['hue_port'])
        result['arcadia_node'] = self._inventory['cdh-worker'][0]
        result['arcadia_port'] = DEFAULT_ARCADIA_PORT
        result['external_tool_arcadia'] = self._check_port(result['arcadia_node'], result['arcadia_port'])
        cluster_name = deployment_settings['clusters'][0]['name']
        result['import_hadoop_conf_hdfs'] = self._get_client_config_for_service('HDFS', cluster_name)
        result['import_hadoop_conf_hbase'] = self._get_client_config_for_service('HBASE', cluster_name)
        result['import_hadoop_conf_yarn'] = self._get_client_config_for_service('YARN', cluster_name)
        result['import_hadoop_conf_hive'] = self._get_client_config_for_service('HIVE', cluster_name)
        return result

    def _get_java_http_proxy(self):
        http_proxy = self._get_ansible_var('http_proxy')
        https_proxy = self._get_ansible_var('https_proxy')
        no_proxy = self._get_ansible_var('no_proxy')

        http_proxy_host, http_proxy_port = self._parse_url_if_not_empty(http_proxy)
        https_proxy_host, https_proxy_port = self._parse_url_if_not_empty(https_proxy)
        non_proxy_hosts = self._convert_no_proxy_to_java_style(no_proxy)

        return (self._fill_if_var_not_empty('-Dhttp.proxyHost={} ', http_proxy_host) + \
               self._fill_if_var_not_empty('-Dhttp.proxyPort={} ', http_proxy_port) + \
               self._fill_if_var_not_empty('-Dhttps.proxyHost={} ', https_proxy_host) + \
               self._fill_if_var_not_empty('-Dhttps.proxyPort={} ', https_proxy_port) + \
               self._fill_if_var_not_empty('-Dhttp.nonProxyHosts={} ', non_proxy_hosts)).strip()

    def _parse_url_if_not_empty(self, url):
        if url:
            splitted = urlparse.urlsplit(url)
            return splitted.hostname, splitted.port
        else:
            return '', ''

    def _convert_no_proxy_to_java_style(self, no_proxy):
        if not no_proxy:
            return ''
        no_proxy = re.sub(r'^\.', '*.', no_proxy)
        no_proxy = no_proxy.replace(',.', '|*.')
        no_proxy = no_proxy.replace(',', '|')
        no_proxy += '|localhost|127.*|[::1]' #these entries don't reside in /etc/ansible/hosts
        return no_proxy

    def _fill_if_var_not_empty(self, template, value):
        return template.format(value) if value else ''

    def _get_mac_address(self):
        output = self._execute_command('curl http://169.254.169.254/latest/meta-data/network/interfaces/macs/')
        return return_fixed_output(output)

    def _get_vpc_id(self):
        mac_address = self._get_mac_address()
        output = self._execute_command('curl http://169.254.169.254/latest/meta-data/network/interfaces/macs/{}/vpc-id'
                                       .format(mac_address))
        return return_fixed_output(output)

    def _generate_inventory(self, workers_count, masters_count, envname):
        hosts = {
            'cdh-master': [],
            'cdh-worker': [],
            'cdh-manager': []
        }
        for i in range(workers_count):
            hosts['cdh-worker'].append('cdh-worker-{}.node.{}.consul'.format(i, envname))
        for i in range(masters_count):
            hosts['cdh-master'].append('cdh-master-{}.node.{}.consul'.format(i, envname))
        hosts['cdh-manager'].append(hosts['cdh-master'][2])
        return hosts

    def _execute_command(self, command):
        if self._ssh_required:
            self._logger.info('Calling remote command: %s', command)
            ssh_in, ssh_out, ssh_err = self._ssh_connection.exec_command(command, get_pty=True)
            return ssh_out.read() if ssh_out else ssh_err.read()
        else:
            self._logger.info('Calling local command: %s', command)
            return subprocess.check_output(command.split())

    def _generate_script(self, script, target):
        with tempfile.NamedTemporaryFile('w') as f:
            f.file.write(script)
            f.file.close()
            if self._ssh_required:
                sftp = self._ssh_connection.open_sftp()
                sftp.put(f.name, target)
            else:
                shutil.copyfile(f.name, target)

    def _generate_keytab(self, principal_name):
        self._logger.info('Generating keytab for {} principal.'.format(principal_name))

        self._generate_script(GENERATE_KEYTAB_SCRIPT, '/tmp/generate_keytab_script.sh')

        COPY_KEYTAB_SCRIPT = 'sudo -i scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' \
                             '/tmp/generate_keytab_script.sh {}@{}:/tmp/'.format(self._cdh_manager_ssh_user,
                                                                                 self._cdh_manager_hostname)

        if self._ssh_required:
            CHMOD_KEYTAB_SCRIPT = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' \
                                  '"chmod 700 /tmp/generate_keytab_script.sh"'.format(self._cdh_manager_ssh_user,
                                                                                      self._cdh_manager_hostname)
            EXECUTE_KEYTAB_SCRIPT = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' \
                                    '"/tmp/generate_keytab_script.sh {}"'.format(self._cdh_manager_ssh_user,
                                                                                 self._cdh_manager_hostname,
                                                                                 principal_name)
        else:
            CHMOD_KEYTAB_SCRIPT = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' \
                                  'chmod 700 /tmp/generate_keytab_script.sh'.format(self._cdh_manager_ssh_user,
                                                                                    self._cdh_manager_hostname)
            EXECUTE_KEYTAB_SCRIPT = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' \
                                    '/tmp/generate_keytab_script.sh {}'.format(self._cdh_manager_ssh_user,
                                                                               self._cdh_manager_hostname,
                                                                               principal_name)

        try:
            self._execute_command(COPY_KEYTAB_SCRIPT)
            self._execute_command(CHMOD_KEYTAB_SCRIPT)
            keytab_hash = self._execute_command(EXECUTE_KEYTAB_SCRIPT)
        except subprocess.CalledProcessError as e:
            self._logger.error('Process failed with exit code %s and output %s', e.returncode, e.output)
            raise e

        keytab_hash = return_fixed_output(keytab_hash)
        self._logger.info('Keytab for %s principal has been generated.', principal_name)
        return keytab_hash

    def _check_port(self, hostname, port):
        self._logger.info('Check is port %d open on %s machine.', port, hostname)
        port_checker_script = PORT_CHECKER_SCRIPT.format(hostname=hostname, port=port)
        self._generate_script(port_checker_script, '/tmp/check_port.py')
        status = int(return_fixed_output(self._execute_command('sudo -i python /tmp/check_port.py')))
        return False if status else True

    def _generate_base64_for_file(self, file_path):
        self._logger.info('Generating base64 for %s file.', file_path)
        if self._ssh_required:
            GENERATE_BASE_64 = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null ' \
                               '-o StrictHostKeyChecking=no "base64 {}"' \
                .format(self._cdh_manager_ssh_user, self._cdh_manager_hostname, file_path)
        else:
            GENERATE_BASE_64 = 'sudo -i ssh -tt {}@{} -o UserKnownHostsFile=/dev/null ' \
                               '-o StrictHostKeyChecking=no base64 {}' \
                .format(self._cdh_manager_ssh_user, self._cdh_manager_hostname, file_path)

        base64_file_hash = self._execute_command(GENERATE_BASE_64)
        base64_file_hash = return_fixed_output(base64_file_hash)
        self._logger.info('Base64 hash for %s file on %s machine has been generated.', file_path,
                          self._cdh_manager_hostname)
        return base64_file_hash

    def _get_client_config_for_service(self, service_name, cluster_name):
        self._execute_command('wget http://{}:{}/api/v10/clusters/{}/services/{}/clientConfig '
                              '--password {} --user {} -P {}'
                              .format(self._cdh_manager_hostname, self._cdh_manager_port, cluster_name, service_name,
                                      self._cdh_manager_password, self._cdh_manager_user, service_name))
        base64_file_hash = self._execute_command('base64 {}/clientConfig'.format(service_name))
        self._execute_command('rm -r {}'.format(service_name))
        result = base64_file_hash.splitlines()
        return ''.join(result)

    def _determine_smtp_protocol(self, port):
        self._logger.info('Determining mail protocol')
        if port in (465,):
            return 'smtps'
        elif port in (25, 587, 2525):
            return 'smtp'
        else:
            self._logger.info('Custom mail port is set, '
                              'set your mail protocol manually in template_variables.yml file and run script once again!')
            return None

    def _find_item_by_attr_value(self, attr_value, attr_name, array_with_dicts):
        try:
            return next(item for item in array_with_dicts if item[attr_name] == attr_value)
        except StopIteration:
            return dict()

    def _get_host(self, service_name, role_name, settings):
        hdfs_service = self._find_item_by_attr_value(service_name, 'name', settings['clusters'][0]['services'])
        hdfs_namenode = self._find_item_by_attr_value(role_name, 'name', hdfs_service['roles'])
        host_id = hdfs_namenode['hostRef']['hostId']
        return self._find_item_by_attr_value(host_id, 'hostId', settings['hosts'])

    def _get_property_value(self, config, key):
        properties = ET.fromstring('<properties>' + config + '</properties>')
        for property in properties:
            if property.find('name').text == key:
                return property.find('value').text
