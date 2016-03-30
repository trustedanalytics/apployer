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
Cloud Foundry REST API client. Has functionality that cannot be achieved through CF CLI.
"""


# class CfApi(object):
#     """
#     Cloud Foundry REST API client. It can refresh it's token.
#     """
#
#     def get_upsi_config(self):
#         raise NotImplementedError()
#
#     def get_upsi_bindings(self):
#         raise NotImplementedError()
#
#     def _refresh_token(self):
#         raise NotImplementedError()
