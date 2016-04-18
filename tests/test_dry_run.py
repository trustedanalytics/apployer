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
from apployer import dry_run
from . import fake_module


def test_provide_dry_run_module(monkeypatch):
    exceptions = ['some_function_d']
    mock_dry_run_log = MagicMock()
    monkeypatch.setattr('apployer.dry_run._log', mock_dry_run_log)

    dry_run_fake_module = dry_run.provide_dry_run_module(fake_module, exceptions)
    dry_run_fake_module.some_function_a('param 1', 'param 2')
    dry_run_fake_module.some_function_b(1)
    dry_run_fake_module.some_function_c()
    assert dry_run_fake_module.some_function_d() == fake_module.FUNC_D_RETURN
    assert dry_run_fake_module._some_function_e() == fake_module.FUNC_E_RETURN

    assert len(mock_dry_run_log.info.call_args_list) == 3
    first_call = mock_dry_run_log.info.call_args_list[0]
    log_func_name = 'some_function_a'
    log_func_params = {'param_a_1': 'param 1', 'param_a_2': 'param 2'}
    assert first_call[0][0].count('%s') == 2
    assert first_call[0][1] == log_func_name
    assert first_call[0][2] == log_func_params

@mock.patch('apployer.dry_run._log.info')
def test_get_dry_run_cf_cli_app_restart(info_mock):
    dry_run_cf_cli = dry_run.get_dry_run_cf_cli()
    fake_app_name = 'some-fake-app'
    dry_run_cf_cli.restart(fake_app_name)
    info_mock.assert_called_with('DRY RUN: calling %s with arguments %s', 'restart', {'app_name': fake_app_name})