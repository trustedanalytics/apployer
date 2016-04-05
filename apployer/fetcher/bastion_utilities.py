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

import logging
import os

import paramiko
import yaml


class CFConfExtractor(object):


    DEFAULT_PROVISION_SH_PATH = '~/provision.sh'

    def __init__(self, config):
        self._logger = logging.getLogger(__name__)

        self._hostname = config['machines']['cf-bastion']['hostname']
        self._hostport = config['machines']['cf-bastion']['hostport']
        self._username = config['machines']['cf-bastion']['username']

        key_path = config['machines']['cf-bastion']['key_filename']
        self._key = os.path.expanduser(key_path)
        self._key_password = config['machines']['cf-bastion']['key_password']

        self._is_openstack = config['openstack_env']
        self._path_to_cf_tiny_yml = config['machines']['cf-bastion']['path_to_cf_tiny_yml']
        self._path_to_docker_vpc_yml = config['machines']['cf-bastion']['path_to_docker_vpc_yml']

        self._path_to_provision_sh = config['machines']['cf-bastion']['path_to_provision_sh']

        if self._path_to_provision_sh is None:
            self._path_to_provision_sh = self.DEFAULT_PROVISION_SH_PATH

    def __enter__(self):
        extractor = self
        self._logger.info('Creating connection to Bastion.')
        extractor.create_ssh_connection_to_cf_bastion()
        self._logger.info('Connection to Bastion established.')
        return extractor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection_to_cf_bastion()
        self._logger.info('Connection to Bastion closed.')

    # bastion methods
    def create_ssh_connection_to_cf_bastion(self):
        try:
            self.ssh_connection = paramiko.SSHClient()
            self.ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_connection.connect(self._hostname, username=self._username, key_filename=self._key, password=self._key_password)
        except Exception as exc:
            self._logger.error('Cannot connect to Bastion machine. Check your bastion settings in fetcher_config.yml file and ssh key.')
            raise exc

    def close_connection_to_cf_bastion(self):
        try:
            self.ssh_connection.close()
        except Exception as exc:
            self._logger.error('Cannot close connection to the Bastion machine.')
            raise exc

    def ssh_call_command(self, command):
        self._logger.info('Calling remote command: "{0}"'.format(command))
        ssh_in, ssh_out, ssh_err = self.ssh_connection.exec_command(command)
        return ssh_out.read() if ssh_out is not None else ssh_err.read()

    def _extract_variables(self):
        result = {}
        if self._path_to_cf_tiny_yml is not None and self._path_to_docker_vpc_yml is not None:
            docker_vpc_yml = yaml.load(self.ssh_call_command('cat {0}'.format(self._path_to_docker_vpc_yml)))
            cf_tiny_yml = yaml.load(self.ssh_call_command('cat {0}'.format(self._path_to_cf_tiny_yml)))
        elif self._is_openstack:
            docker_vpc_yml = yaml.load(self.ssh_call_command('cat ~/workspace/deployments/docker-services-boshworkspace/.deployments/docker-openstack.yml'))
            cf_tiny_yml = yaml.load(self.ssh_call_command('cat ~/workspace/deployments/cf-boshworkspace/deployments/cf-openstack-tiny.yml'))
        else:
            docker_vpc_yml = yaml.load(self.ssh_call_command('cat ~/workspace/deployments/docker-services-boshworkspace/.deployments/docker-aws-vpc.yml'))
            cf_tiny_yml = yaml.load(self.ssh_call_command('cat ~/workspace/deployments/cf-boshworkspace/deployments/cf-aws-tiny.yml'))

        if docker_vpc_yml is None or cf_tiny_yml is None:
            raise IOError("Cannot find configuration files on the cf-bastion machine.")

        result['nats_ip'] = docker_vpc_yml['properties']['nats']['machines'][0]
        result['h2o_provisioner_host'] = docker_vpc_yml['jobs'][0]['networks'][0]['static_ips'][0]
        result['h2o_provisioner_port'] = '9876'
        result['cf_admin_password'] = cf_tiny_yml['meta']['admin_secret']
        result['cf_admin_client_password'] = cf_tiny_yml['meta']['secret']
        result['apps_domain'] = cf_tiny_yml['meta']['app_domains']
        result['tap_console_password'] = cf_tiny_yml['meta']['secret']
        result['email_address'] = cf_tiny_yml['meta']['login_smtp']['senderEmail']
        result['run_domain'] = cf_tiny_yml['meta']['domain']
        result['smtp_pass'] = '"{0}"'.format(cf_tiny_yml['meta']['login_smtp']['password'])
        result['smtp_user'] = '"{0}"'.format(cf_tiny_yml['meta']['login_smtp']['user'])
        result['smtp_port'] = cf_tiny_yml['meta']['login_smtp']['port']
        result['smtp_host'] = cf_tiny_yml['meta']['login_smtp']['host']
        result['smtp_protocol'] = self._determine_smtp_protocol(result['smtp_port'])
        result['aws_default_region_name'] = self._fetch_variable_from_provision_sh('REGION')
        result['aws_access_key_id'] = self._fetch_variable_from_provision_sh('AWS_KEY_ID')
        result['aws_secret_access_key'] = self._fetch_variable_from_provision_sh('AWS_ACCESS_KEY')
        result['vpc'] = self._fetch_variable_from_provision_sh('VPC')
        # To replace after finishing https://intel-data.atlassian.net/browse/DPNG-6527
        result['subnet'] = self._fetch_variable_from_provision_sh('CF_SUBNET1')
        #result['subnet'] = self._fetch_variable_from_provision_sh('KUBERNETES_SUBNET')
        #result['kubernetes_subnet_cidr'] = self._fetch_variable_from_provision_sh('KUBERNETES_SUBNET_IP')
        result['key_name'] = self._fetch_key_name_from_aws()
        result['consul_dc'] = self._fetch_variable_from_provision_sh('ENV_NAME')
        result['consul_join'] = self._fetch_variable_from_provision_sh('CONSUL_MASTERS')
        return result

    def get_environment_settings(self):
        return self._extract_variables()

    def _determine_smtp_protocol(self, port):
        self._logger.info('Determining mail protocol')
        if port in (465,):
            return 'smtps'
        elif port in (25, 587, 2525):
            return 'smtp'
        else:
            self._logger.info('Custom mail port is set, set your mail protocol manually '
                             'in template_variables.yml file and run script once again!')
            return None

    def _fetch_variable_from_provision_sh(self, var_name):
        raw_var_assignment = self.ssh_call_command('cat ' + self._path_to_provision_sh + ' | grep ' + var_name + '=')
        var_value = raw_var_assignment.split('=')[1]

        var_value = var_value.translate(None, '\"\n')

        if "," in var_value:
            var_value = var_value.split(',')[0]

        return var_value

    def _fetch_key_name_from_aws(self):
        raw_key_name = self.ssh_call_command('curl 169.254.169.254/latest/meta-data/public-keys/')
        correct_key_name = raw_key_name.split('=')[1]
        return correct_key_name
