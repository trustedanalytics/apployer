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
Common Pytest fixtures.
"""

import os
import zipfile

from testfixtures.popen import MockPopen
import pytest

from .utils import get_appstack_resource_dir


@pytest.yield_fixture
def mock_popen(monkeypatch):
    mock_popen = MockPopen()
    monkeypatch.setattr('apployer.cf_cli.Popen', mock_popen)
    yield mock_popen
    assert mock_popen.mock.method_calls


@pytest.fixture
def artifacts_location(tmpdir):
    artifacts_path = tmpdir.strpath
    resources_path = get_appstack_resource_dir()
    for manifest in [f for f in os.listdir(resources_path) if f.startswith('manifest')]:
        manifest_path = os.path.join(resources_path, manifest)
        app_name = manifest.split('_')[1].split('.')[0]

        # TODO later it should ignore the version in zip files
        zip_path = os.path.join(artifacts_path, app_name + '.zip')
        with zipfile.ZipFile(zip_path, mode='w') as zf:
            zf.write(manifest_path, 'manifest.yml')
    return artifacts_path
