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
from apployer.fetcher.expressions import ExpressionsEngine, InMemoryKeyValueStore


@pytest.fixture
def expression_engine():
    return ExpressionsEngine(InMemoryKeyValueStore())


def test_parse_and_apply_expression_without_executable_expression(expression_engine):
    final_value = expression_engine.parse_and_apply_expression('test_key1', 'simple_value')
    assert final_value == 'simple_value'


def test_parse_and_apply_expression_random(expression_engine):
    final_value = expression_engine.parse_and_apply_expression('test_key2', '%random 8%')
    assert len(final_value) == 8
    assert final_value.isalnum()


def test_parse_and_apply_expression_random_already_exists(expression_engine):
    expression_engine._store.put('test_key3', 'fake_rand_pass')
    final_value = expression_engine.parse_and_apply_expression('test_key3', '%random 14%')
    assert final_value == 'fake_rand_pass'


def test_parse_and_apply_expression_random_many_times_for_the_same_key(expression_engine):
    final_value_first_time = expression_engine.parse_and_apply_expression('test_key4', '%random 10%')
    assert len(final_value_first_time) == 10
    assert final_value_first_time.isalnum()

    final_value_second_time = expression_engine.parse_and_apply_expression('test_key4', '%random 10%')
    assert final_value_first_time == final_value_second_time


def test_parse_and_apply_expression_parsing_with_whitespaces(expression_engine):
    final_value5 = expression_engine.parse_and_apply_expression('test_key5', '  % random 5%')
    final_value6 = expression_engine.parse_and_apply_expression('test_key6', '%random    6%')
    final_value7 = expression_engine.parse_and_apply_expression('test_key7', '%random 7% ')
    final_value8 = expression_engine.parse_and_apply_expression('test_key8', '%random     8% ')
    final_value9 = expression_engine.parse_and_apply_expression('test_key9', ' %  random     9 % ')
    assert len(final_value5) == 5
    assert final_value5.isalnum()
    assert len(final_value6) == 6
    assert final_value6.isalnum()
    assert len(final_value7) == 7
    assert final_value7.isalnum()
    assert len(final_value8) == 8
    assert final_value8.isalnum()
    assert len(final_value9) == 9
    assert final_value9.isalnum()

