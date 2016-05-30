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

"""Module provides expression parsing and execution.
"""

import logging
import re
import random
import string
import subprocess


RANDOM_EXPRESSION_PATTERN = re.compile("^[ \t]*%[ \t]*random[ \t]*([0-9]+)[ \t]*%[ \t]*$")


class InMemoryKeyValueStore(object):
    """Key value store for tests purpose (in-memory).
    """

    def __init__(self):
        self._store = dict()


    def put(self, key, value):
        """Store [value] under [key]. Overwrites previous value.
        """
        self._store[key] = value


    def get(self, key):
        """Get value stored under [key] if it exist, None otherwise.
        """
        return self._store.get(key, None)


class FsKeyValueStore(object):
    """Key value store using file in particular directory as storage system.
    """

    def __init__(self, store_path, ssh_required, ssh_connection):
        def _normalize_path(path):
            return path + ('' if path.endswith('/') else '/')

        self._logger = logging.getLogger(__name__)
        self._store_path = _normalize_path(store_path)
        self._ssh_required = ssh_required
        self._ssh_connection = ssh_connection
        self._execute_command('sudo -i mkdir -p ' + self._store_path)


    def _execute_command(self, command):
        if self._ssh_required:
            self._logger.info('Calling remote command: %s', command)
            _, ssh_out, ssh_err = self._ssh_connection.exec_command(command, get_pty=True)
            return ssh_out.read() if ssh_out else ssh_err.read()
        else:
            self._logger.info('Calling local command: %s', command)
            return subprocess.check_output(command.split())


    def put(self, key, value):
        """Store [value] in file named [key]. Overwrites previous file.
        """
        self._execute_command('sudo -i bash -c \'echo -n "{0}" > {1}{2}\''
                              .format(value, self._store_path, key))


    def get(self, key):
        """Get value stored in file named [key] if it exist, None otherwise.
        """
        output = self._execute_command(
            'sudo -i bash -c \'if [ -f "{0}" ]; then cat "{0}"; else echo -n "FILE_NOT_FOUND"; fi\''
            .format(self._store_path + key))
        value = return_fixed_output(output)
        return None if value == 'FILE_NOT_FOUND' else value


class ExpressionsEngine(object):
    """Parses and executes expression.
    Currently there is one expression type available:
        "%random n%" which generates random alphanumeric string of length n.
    """

    def __init__(self, key_value_store):
        self._store = key_value_store


    def parse_and_apply_expression(self, key, value):
        """Parses value read from appstack and apply expression if it is recognized as expression.

        Args:
            key (str): key read from appstack.
            value (str): value read from appstack.

        Returns:
            str: unchanged value if it does not match any expression pattern,
                    or applied expression otherwise.
        """
        if RANDOM_EXPRESSION_PATTERN.match(str(value)):
            return self._store.get(key) or self._genarate_and_save_random(key, value)
        return value


    def _genarate_and_save_random(self, key, value):
        random_string_length = int(RANDOM_EXPRESSION_PATTERN.split(value)[1])
        random_string = generate_random_alphanumeric(random_string_length)
        self._store.put(key, random_string)
        return random_string


def return_fixed_output(output, rstrip=True):
    """ Filters output string from any know warnings.

    Args:
        output (string): string to be filtered.
        rstrip (bool): when set to True, output will be joined without new line for each entry.

    Returns:
        str: filtered output without any know warnings.
    """
    fixed_output = filter(_non_debug_line, output.split('\r\n'))
    joiner = '' if rstrip else '\r\n'
    return joiner.join(fixed_output)


def _non_debug_line(line):
    return 'unable to resolve' not in line \
            and 'Warning:' not in line \
            and 'Connection to' not in line


def generate_random_alphanumeric(length):
    """ Generates random string of given length.

    Args:
        length (int): length of string to be generated

    Returns:
        str: randomly generated string of given length
    """
    return ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) \
                   for _ in range(length))
