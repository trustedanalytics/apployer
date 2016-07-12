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

import json

from mock import MagicMock
import mock
import pytest

from apployer import cf_api, cf_cli


@mock.patch('subprocess.check_output')
def test_cf_curl_get(check_output_mock):
    api_path = '/v2/blabla'
    response_body = '{"a": "b"}'
    check_output_mock.return_value = response_body

    assert cf_api._cf_curl_get(api_path) == json.loads(response_body)
    check_output_mock.assert_called_with('cf curl {}'.format(api_path).split(' '))


@mock.patch('subprocess.check_output')
def test_cf_curl_get_error(check_output_mock):
    api_path = '/v2/blabla'
    response_body = '{"error_code": "CF-SomeError"}'
    check_output_mock.return_value = response_body

    with pytest.raises(cf_cli.CommandFailedError):
        cf_api._cf_curl_get(api_path)
    check_output_mock.assert_called_with('cf curl {}'.format(api_path).split(' '))


UPSI_CONFIG = """{
  "metadata": {
    "guid": "e0687b7b-ce3e-43b9-a62a-eda2d77bd55b",
    "url": "/v2/user_provided_service_instances/e0687b7b-ce3e-43b9-a62a-eda2d77bd55b",
    "created_at": "2016-03-17T21:41:17Z",
    "updated_at": null
  },
  "entity": {
    "name": "name-993",
    "credentials": {
      "creds-key-44": "creds-val-44"
    },
    "space_guid": "63d7920e-a1f1-434b-bef9-988c9fb41989",
    "type": "user_provided_service_instance",
    "syslog_drain_url": "https://foo.com/url-38",
    "route_service_url": null,
    "space_url": "/v2/spaces/63d7920e-a1f1-434b-bef9-988c9fb41989",
    "service_bindings_url": "/v2/user_provided_service_instances/e0687b7b-ce3e-43b9-a62a-eda2d77bd55b/service_bindings",
    "routes_url": "/v2/user_provided_service_instances/e0687b7b-ce3e-43b9-a62a-eda2d77bd55b/routes"
  }
}"""


def test_get_upsi_config(monkeypatch):
    service_guid = 'some-fake-guid'
    mock_cf_curl_get = MagicMock(return_value=json.loads(UPSI_CONFIG))
    monkeypatch.setattr('apployer.cf_api._cf_curl_get', mock_cf_curl_get)

    assert cf_api.get_upsi_credentials(service_guid) == {'creds-key-44': 'creds-val-44'}
    mock_cf_curl_get.assert_called_with(
        '/v2/user_provided_service_instances/{}'.format(service_guid))


BINDINGS = """[
    {
        "metadata": {
            "guid": "968574fc-dda9-4ccf-b5ca-3e7af772c8ae",
            "url": "/v2/service_bindings/968574fc-dda9-4ccf-b5ca-3e7af772c8ae",
            "created_at": "2015-08-05T19:17:22Z",
            "updated_at": null
        },
        "entity": {
            "app_guid": "593505c5-f535-4690-9f06-8edfa2d27450",
            "service_instance_guid": "8b89a54b-b292-49eb-a8c4-2396ec038120",
            "credentials": {
                "host": "https://data-catalog.gotapaas.eu"
            },
            "binding_options": {},
            "gateway_data": null,
            "gateway_name": "",
            "syslog_drain_url": "",
            "app_url": "/v2/apps/593505c5-f535-4690-9f06-8edfa2d27450",
            "service_instance_url": "/v2/user_provided_service_instances/8b89a54b-b292-49eb-a8c4-2396ec038120"
        }
    },
    {
        "metadata": {
            "guid": "99ba4513-de87-47ab-bf34-d5e244af46fe",
            "url": "/v2/service_bindings/99ba4513-de87-47ab-bf34-d5e244af46fe",
            "created_at": "2015-08-05T19:52:41Z",
            "updated_at": null
        },
        "entity": {
            "app_guid": "2cbd0b13-e1d8-4e9f-ae63-7940d323332d",
            "service_instance_guid": "8b89a54b-b292-49eb-a8c4-2396ec038120",
            "credentials": {
                "host": "https://data-catalog.gotapaas.eu"
            },
            "binding_options": {},
            "gateway_data": null,
            "gateway_name": "",
            "syslog_drain_url": "",
            "app_url": "/v2/apps/2cbd0b13-e1d8-4e9f-ae63-7940d323332d",
            "service_instance_url": "/v2/user_provided_service_instances/8b89a54b-b292-49eb-a8c4-2396ec038120"
        }
    }
]"""

BINDINGS_RESPONSE = """{{
    "total_results": 5,
    "total_pages": 1,
    "prev_url": null,
    "next_url": null,
    "resources": {}
}}""".format(BINDINGS)


def test_get_upsi_bindings(monkeypatch):
    service_guid = 'some-fake-guid'
    mock_cf_curl_get = MagicMock(return_value=json.loads(BINDINGS_RESPONSE))
    monkeypatch.setattr('apployer.cf_api._cf_curl_get', mock_cf_curl_get)

    assert cf_api.get_upsi_bindings(service_guid) == json.loads(BINDINGS)
    mock_cf_curl_get.assert_called_with(
            '/v2/user_provided_service_instances/{}/service_bindings'.format(service_guid))


BINDING_URL = "/v2/service_bindings/235ca6b9-bf75-4c14-b546-dd186bb674fb"
SERVICE_BINDING = {
    "metadata": {
        "guid": "235ca6b9-bf75-4c14-b546-dd186bb674fb",
        "url": "/v2/service_bindings/235ca6b9-bf75-4c14-b546-dd186bb674fb",
        "some_more_stuff": "true... true..."
    },
    "entity": {
        "app_guid": "50c32f81-5432-495a-aae3-0697e39fed36",
        "service_instance_guid": "8b89a54b-b292-49eb-a8c4-2396ec038120",
        "some_more_stuff": "yeah..."
    }
}


@mock.patch('subprocess.check_output')
def test_delete_service_binding(check_output_mock):
    check_output_mock.return_value = ''

    cf_api.delete_service_binding(SERVICE_BINDING)

    check_output_mock.assert_called_with('cf curl {} -X DELETE'.format(BINDING_URL).split(' '))


@mock.patch('subprocess.check_output')
def test_delete_service_binding_error(check_output_mock):
    check_output_mock.return_value = '{"some": "output"}'

    with pytest.raises(cf_cli.CommandFailedError):
        cf_api.delete_service_binding(SERVICE_BINDING)

    check_output_mock.assert_called_with('cf curl {} -X DELETE'.format(BINDING_URL).split(' '))


@mock.patch('subprocess.check_output')
def test_create_service_binding(check_output_mock):
    service_guid = 'some-fake-guid'
    app_guid = 'some-other-fake-guid'
    params = json.dumps({'service_instance_guid': service_guid, 'app_guid': app_guid})
    check_output_mock.return_value = '{"some": "output"}'

    cf_api.create_service_binding(service_guid, app_guid)

    check_output_mock.assert_called_with('cf curl /v2/service_bindings -X POST -d'.split(' ') + [params])


@mock.patch('subprocess.check_output')
def test_create_service_binding_error(check_output_mock):
    service_guid = 'some-fake-guid'
    app_guid = 'some-other-fake-guid'
    params = json.dumps({'service_instance_guid': service_guid, 'app_guid': app_guid})
    check_output_mock.return_value = '{"error_code": "CF-something"}'

    with pytest.raises(cf_cli.CommandFailedError):
        cf_api.create_service_binding(service_guid, app_guid)
    check_output_mock.assert_called_with('cf curl /v2/service_bindings -X POST -d'.split(' ') + [params])


@mock.patch('subprocess.check_output')
def test_get_app_name(check_output_mock):
    app_guid = 'some-fake-guid'
    app_name = 'some-fake-name'
    app_description = """{
  "metadata": {
    "guid": "some-fake-guid",
    "url": "/v2/apps/02a7f900-e8b8-4a8f-93b8-ecfd9f2a194a",
    "created_at": "2016-03-17T21:41:12Z",
    "updated_at": "2016-03-17T21:41:12Z"
  },
  "entity": {
    "name": "some-fake-name",
    "some": "other stuff..."
  }
}
"""
    check_output_mock.return_value = app_description

    assert cf_api.get_app_name(app_guid) == app_name
    check_output_mock.assert_called_with('cf curl /v2/apps/{}'.format(app_guid).split(' '))
