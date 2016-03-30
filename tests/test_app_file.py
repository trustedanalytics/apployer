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

import pytest

from apployer.app_file import get_artifact_name, get_file_path


@pytest.mark.parametrize('zip_name, artifact_name', [
    ('some-thing.zip', 'some-thing'),
    ('some-thing-0.1.2.zip', 'some-thing'),
    ('bla-0.1.dev0345asd.zip', 'bla'),
    ('a-vocado-v0.1.dev0345asd.zip', 'a-vocado'),
    ('/xxx/yyy/a-vocado-v0.1.dev0345asd.zip', 'a-vocado'),
    ('tap-java-buildpack-v3.4-5.zip', 'tap-java-buildpack'),
])
def test_get_artifact_name(zip_name, artifact_name):
    assert get_artifact_name(zip_name) == artifact_name


def test_get_file_path(tmpdir):
    test_dir = tmpdir.mkdir('test_get_file_path')
    test_file = test_dir.join('some-test-file')
    test_file.ensure(file=True)

    assert get_file_path('some-tes', test_dir.strpath) == test_file.strpath


def test_get_file_path_not_found(tmpdir):
    test_dir = tmpdir.mkdir('test_get_file_path')
    test_dir.ensure(dir=True)

    with pytest.raises(IOError):
        get_file_path('some-nonexistint-file', test_dir.strpath)
