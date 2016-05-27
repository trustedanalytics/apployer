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

GET_ENV_SUCCESS = """
Getting env variables for app data-catalog in org seedorg / space seedspace as michal.bultrowicz@intel.com...
OK

System-Provided:
{
 "VCAP_SERVICES": {

}

{
 "VCAP_APPLICATION": {
  "application_name": "FAKYFAKE"
 }
}

User-Provided:
LOG_LEVEL: INFO
VERSION: 6.6.6

No running env variables have been set

No staging env variables have been set

"""

GET_SERVICE_INFO_SUCCESS = """

Service instance: bla
Service: user-provided
"""
