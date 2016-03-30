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
Utilities for handling application artifacts.
"""

import os
from os import path
import re


# match all up to a dash followed by a "v" and a digit or by a digit only (e.g. -0, -v1)
_ARTIFACT_NAME_EXTRACTOR = re.compile(r'(.*?)(?:\-v?\d)')


def get_artifact_name(artifact_zip_path):
    """Get's an artifact name (the name of the project the application is created from) from the
        artifact's path.

    Args:
        artifact_zip_path (str): Path of the aftifact file.

    Returns:
        str: Artifact's name.
    """
    artifact_zip_name = path.basename(artifact_zip_path)
    match = _ARTIFACT_NAME_EXTRACTOR.match(artifact_zip_name)
    if match:
        return match.groups()[0]
    else:
        return artifact_zip_name.split('.')[0]


def get_file_path(file_part_name, directory):
    """Gets the full path to a file from `directory` with `file_part_name` in its name.
    Only the first path is returned if there's more than one match.

    Args:
        file_part_name (str): Part of the file's name.
        directory (str): Directory in which the file should be found.

    Returns:
        str: Full path to the file.

    Raises
        IOError: File wasn't found in the directory.
    """
    full_dir = path.realpath(directory)
    for file_name in os.listdir(full_dir):
        if file_part_name in file_name:
            return path.join(full_dir, file_name)
    raise IOError('File with partial name "{}" not found in directory "{}"'
                  .format(file_part_name, full_dir))
