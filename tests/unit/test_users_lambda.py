# Copyright (c) RACSOCE. All rights reserved.
"""
Unit tests for the Customers Lambda — get_customer, update_customer,
and delete_customer handlers (task 5.3).

Uses moto to mock DynamoDB so no real AWS credentials are required.
"""

import json
import os

import boto3
import pytest
from moto import mock_aws

# Point the module at a fake table name before importing the Lambda
os.environ.setdefault("DYNAMODB_TABLE_NAME", "customers-test")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TABLE_NAME = "customers-test"

_SAMPLE_ITEM = {
    "customer_id": "aaaaaaaa-0000-0000-0000-000000000001",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane.doe@example.com",
    "phone": "+15551234567",
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z",
}


def _make_event(method: str, customer_id: str | None = None, body: dict | None = None) -> dict:
    """Build a minimal API Gateway proxy event."""
    event: dict = {
        "httpMethod": method,
        "pathParameters": {"customer_id": customer_id} if customer_id else None,
        "requestContext": {"requestId": "test-request-id-123"},
        "body": json.dumps(body) if body is not None else None,
    }
    return event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Ensure boto3 never hits real AWS."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", _TABLE_NAME)


@pytest.fixture()
def ddb_table():
    """Create a mocked DynamoDB table and yield the boto3 Table resource."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[{"AttributeName": "customer_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "customer_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


def _seed(table, item: dict | None = None) -> dict:
    """Insert a customer item into the table and return it."""
    record = item or _SAMPLE_ITEM.copy()
    table.put_item(Item=record)
    return record


# ---------------------------------------------------------------------------
# get_customer
# ---------------------------------------------------------------------------

class TestGetCustomer:
    def test_returns_200_with_resource_envelope(self, ddb_table):
        _seed(ddb_table)
        # Re-import inside mock context so _table points at the mocked resource
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("GET", customer_id=_SAMPLE_ITEM["customer_id"])
        response = lf.get_customer(event)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "data" in body
        data = body["data"]
        assert data["id"] == _SAMPLE_ITEM["customer_id"]
        assert data["type"] == "customer"
        assert data["attributes"]["first_name"] == "Jane"
        assert data["attributes"]["email"] == "jane.doe@example.com"

    def test_returns_404_when_not_found(self, ddb_table):
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("GET", customer_id="nonexistent-id")
        response = lf.get_customer(event)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"]["code"] == "resource_not_found"

    def test_includes_phone_when_present(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("GET", customer_id=_SAMPLE_ITEM["customer_id"])
        response = lf.get_customer(event)

        body = json.loads(response["body"])
        assert body["data"]["attributes"]["phone"] == "+15551234567"

    def test_omits_phone_when_absent(self, ddb_table):
        item = {k: v for k, v in _SAMPLE_ITEM.items() if k != "phone"}
        _seed(ddb_table, item)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("GET", customer_id=item["customer_id"])
        response = lf.get_customer(event)

        body = json.loads(response["body"])
        assert "phone" not in body["data"]["attributes"]


# ---------------------------------------------------------------------------
# update_customer
# ---------------------------------------------------------------------------

class TestUpdateCustomer:
    _UPDATE_BODY = {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
    }

    def test_returns_200_with_updated_resource(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=self._UPDATE_BODY)
        response = lf.update_customer(event)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        attrs = body["data"]["attributes"]
        assert attrs["first_name"] == "John"
        assert attrs["last_name"] == "Smith"
        assert attrs["email"] == "john.smith@example.com"

    def test_preserves_created_at(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=self._UPDATE_BODY)
        response = lf.update_customer(event)

        body = json.loads(response["body"])
        assert body["data"]["attributes"]["created_at"] == _SAMPLE_ITEM["created_at"]

    def test_updates_updated_at(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=self._UPDATE_BODY)
        response = lf.update_customer(event)

        body = json.loads(response["body"])
        # updated_at must be a valid ISO 8601 string and >= original
        new_updated_at = body["data"]["attributes"]["updated_at"]
        assert new_updated_at >= _SAMPLE_ITEM["updated_at"]

    def test_returns_404_when_not_found(self, ddb_table):
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("PUT", customer_id="nonexistent-id", body=self._UPDATE_BODY)
        response = lf.update_customer(event)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"]["code"] == "resource_not_found"

    def test_returns_400_on_missing_required_field(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        bad_body = {"first_name": "John", "last_name": "Smith"}  # missing email
        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=bad_body)
        response = lf.update_customer(event)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "validation_failed"

    def test_returns_400_on_invalid_email(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        bad_body = {"first_name": "John", "last_name": "Smith", "email": "not-an-email"}
        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=bad_body)
        response = lf.update_customer(event)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "validation_failed"

    def test_returns_400_on_malformed_json(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"])
        event["body"] = "{not valid json"
        response = lf.update_customer(event)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------------------
# delete_customer
# ---------------------------------------------------------------------------

class TestDeleteCustomer:
    def test_returns_204_with_empty_body(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("DELETE", customer_id=_SAMPLE_ITEM["customer_id"])
        response = lf.delete_customer(event)

        assert response["statusCode"] == 204
        assert response["body"] == ""

    def test_item_is_removed_from_dynamodb(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("DELETE", customer_id=_SAMPLE_ITEM["customer_id"])
        lf.delete_customer(event)

        # Confirm the item is gone
        result = ddb_table.get_item(Key={"customer_id": _SAMPLE_ITEM["customer_id"]})
        assert "Item" not in result

    def test_returns_404_when_not_found(self, ddb_table):
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("DELETE", customer_id="nonexistent-id")
        response = lf.delete_customer(event)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"]["code"] == "resource_not_found"

    def test_second_delete_returns_404(self, ddb_table):
        """Deleting the same customer twice should 404 on the second attempt."""
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("DELETE", customer_id=_SAMPLE_ITEM["customer_id"])
        lf.delete_customer(event)
        response = lf.delete_customer(event)

        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# lambda_handler routing
# ---------------------------------------------------------------------------

class TestLambdaHandlerRouting:
    def test_routes_get_with_id_to_get_customer(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("GET", customer_id=_SAMPLE_ITEM["customer_id"])
        response = lf.lambda_handler(event, None)
        assert response["statusCode"] == 200

    def test_routes_put_with_id_to_update_customer(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        body = {"first_name": "X", "last_name": "Y", "email": "x.y@example.com"}
        event = _make_event("PUT", customer_id=_SAMPLE_ITEM["customer_id"], body=body)
        response = lf.lambda_handler(event, None)
        assert response["statusCode"] == 200

    def test_routes_delete_with_id_to_delete_customer(self, ddb_table):
        _seed(ddb_table)
        from importlib import reload
        import src.users.lambda_function as lf
        reload(lf)

        event = _make_event("DELETE", customer_id=_SAMPLE_ITEM["customer_id"])
        response = lf.lambda_handler(event, None)
        assert response["statusCode"] == 204
