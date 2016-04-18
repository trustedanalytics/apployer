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
Fake module for testing substitution of cf_cli module to a dry run version.
"""


FUNC_D_RETURN = "I'm the output of a function that shouldn't be replaced."
FUNC_E_RETURN = "I'm the output of another function that shouldn't be replaced."


def some_function_a(param_a_1, param_a_2):
    print(param_a_1 + param_a_2)


def some_function_b(param_b_1):
    print(param_b_1)


def some_function_c():
    print("I'm a parameterless function.")


def some_function_d():
    return FUNC_D_RETURN


def _some_function_e():
    return FUNC_E_RETURN
