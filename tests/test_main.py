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

import mock
from mock import MagicMock

import pytest

from apployer.main import _get_filled_appstack, ApployerArgumentError, _seconds_to_time

appstack_path = 'appstack_path'
expanded_appstack_path = 'expanded_appstack_path'
filled_appstack_path = 'filled_appstack_path'
artifacts_path = 'artifacts_path'
fetcher_conf_path = 'fetcher_conf_path'


@pytest.fixture
def mock_appstack_file(monkeypatch):
    monkeypatch.setattr('__builtin__.open', mock.mock_open(read_data='{}'))


@pytest.fixture
def mock_fill_appstack(monkeypatch):
    mock_fill = MagicMock()
    monkeypatch.setattr('apployer.main.fill_appstack', mock_fill)
    return mock_fill


@pytest.fixture
def mock_expand_appstack(monkeypatch):
    mock_expand = MagicMock()
    monkeypatch.setattr('apployer.main.expand_appstack', mock_expand)
    return mock_expand


def test_get_filled_appstack_with_filled(monkeypatch, mock_appstack_file):
    monkeypatch.setattr(
        'os.path.exists',
        lambda path: True if path == filled_appstack_path else False)
    _get_filled_appstack(None, None, filled_appstack_path, None, None, 'other')


def test_get_filled_appstack_with_expanded(monkeypatch, mock_appstack_file, mock_fill_appstack):
    monkeypatch.setattr(
        'os.path.exists',
        lambda path: True if path == expanded_appstack_path else False)
    _get_filled_appstack(None, expanded_appstack_path, None, fetcher_conf_path, artifacts_path, 'other')
    mock_fill_appstack.assert_called_once_with(expanded_appstack_path, fetcher_conf_path)


def test_get_filled_appstack_with_bare(monkeypatch, mock_appstack_file,
                                       mock_fill_appstack, mock_expand_appstack):
    monkeypatch.setattr(
        'os.path.exists',
        lambda path: True if path == appstack_path else False)

    _get_filled_appstack(appstack_path, expanded_appstack_path, None,
                         fetcher_conf_path, artifacts_path, 'other')

    mock_expand_appstack.assert_called_once_with(appstack_path, artifacts_path,
                                                 expanded_appstack_path, 'other')
    mock_fill_appstack.assert_called_once_with(expanded_appstack_path, fetcher_conf_path)


def test_get_filled_appstack_with_none(monkeypatch):
    monkeypatch.setattr('os.path.exists', lambda path: False)
    with pytest.raises(ApployerArgumentError):
        _get_filled_appstack(None, None, None, None, None, None)


@pytest.mark.parametrize('string, seconds', [
    ('0:02:03', 123.3),
    ('0:12:13', 733),
    ('453:56:33', 1634193.23454)
])
def test_seconds_to_time(string, seconds):
    assert string == _seconds_to_time(seconds)
