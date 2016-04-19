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
Deduction of some configuration variables based on those already fetched.
"""

THRIFT_SERVER_URL = 'thrift_server_url'
HIVE_SERVER_URL = 'hive_server_url'


def deduce_final_configuration(fetched_config):
    """ Fills some variables in configuration based on those already extracted.
    Args:
        fetched_config (dict): Configuration variables extracted from a living environment,

    Returns:
        dict: Final configuration from live environment.
    """
    final_config = fetched_config.copy()
    final_config[THRIFT_SERVER_URL] = _get_thrift_server_url(final_config)
    final_config[HIVE_SERVER_URL] = _get_hive_server_url(final_config)
    return final_config

def _get_hive_server_url(config):
    if config['kerberos_host']:
        return ('jdbc:hive2://{namenode_internal_host}:10000/default;'
                'principal=hive/{namenode_internal_host}@{kerberos_realm};'
                'auth=kerberos'.format(**config))
    else:
        return 'jdbc:hive2://{namenode_internal_host}:10000/'.format(**config)

def _get_thrift_server_url(config):
    if not config['external_tool_arcadia']:
        return _get_hive_server_url(config)
    else:
        if config['kerberos_host']:
            return ('jdbc:hive2://{arcadia_node}:31050/;'
                    'principal=arcadia-user/{arcadia_node}@{kerberos_realm};'
                    'auth=kerberos'.format(**config))
        else:
            return 'jdbc:hive2://{arcadia_node}:31050/;auth=noSasl'.format(**config)
