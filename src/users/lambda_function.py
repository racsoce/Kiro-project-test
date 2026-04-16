# Copyright (c) RACSOCE. All rights reserved.
"""
Customers Lambda — request router and CRUD handler.

Routes incoming API Gateway proxy events by HTTP method and the presence
of ``pathParameters`` to the appropriate operation handler.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from src.shared.response import (
    build_collection_response,
    build_error_response,
    build_success_response,
)
from src.users.validation import (
    InvalidRequestError,
    ValidationError,
    parse_body,
    validate_customer_payload,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# DynamoDB resource (module-level so the connection is reused across
# warm Lambda invocations)
# ---------------------------------------------------------------------------

_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "customers")
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)

# ---------------------------------------------------------------------------
# Response headers (re-exported from shared for convenience)
# ---------------------------------------------------------------------------

_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string (e.g. ``2024-01-15T10:30:00Z``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_to_resource(item: dict) -> dict:
    """Convert a raw DynamoDB item into a RACSOCE single-resource object."""
    attributes = {
        "first_name": item.get("first_name"),
        "last_name": item.get("last_name"),
        "email": item.get("email"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }
    # Include optional phone only when present
    if "phone" in item:
        attributes["phone"] = item["phone"]

    return {
        "id": item["customer_id"],
        "type": "customer",
        "attributes": attributes,
    }


def _request_id(event: dict) -> str | None:
    """Extract the API Gateway request ID from the event, if available."""
    return (
        event.get("requestContext", {}).get("requestId")
        if isinstance(event.get("requestContext"), dict)
        else None
    )


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def list_customers(event: dict) -> dict:
    """Handle GET /v1/customers — return all customers as a collection envelope.

    Performs a full DynamoDB table scan and returns every item wrapped in
    the RACSOCE collection envelope::

        { "data": [...], "meta": { "total": N } }

    Args:
        event: API Gateway proxy event (unused beyond request ID extraction).

    Returns:
        A Lambda proxy response dict with status 200.
    """
    try:
        response = _table.scan()
        items = response.get("Items", [])

        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = _table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

        resources = [_item_to_resource(item) for item in items]
        envelope = build_collection_response(resources, len(resources))

        return {
            "statusCode": 200,
            "headers": _HEADERS,
            "body": json.dumps(envelope),
        }

    except ClientError as exc:
        logger.error("DynamoDB ClientError in list_customers: %s", exc)
        return build_error_response(
            500,
            "internal_error",
            "An internal error occurred while retrieving customers.",
            _request_id(event),
        )


def create_customer(event: dict) -> dict:
    """Handle POST /v1/customers — validate payload, persist, and return 201.

    Generates a UUID v4 ``customer_id`` and ISO 8601 UTC timestamps for
    ``created_at`` and ``updated_at``, writes the item to DynamoDB, and
    returns the created resource wrapped in the RACSOCE single-resource
    envelope with HTTP 201.

    Args:
        event: API Gateway proxy event containing the JSON request body.

    Returns:
        A Lambda proxy response dict with status 201 on success, or an
        appropriate error response (400 / 500) on failure.
    """
    req_id = _request_id(event)

    try:
        body = parse_body(event)
        validate_customer_payload(body)
    except ValidationError as exc:
        return build_error_response(400, "validation_failed", exc.message, req_id)
    except InvalidRequestError as exc:
        return build_error_response(400, "invalid_request", exc.message, req_id)

    try:
        now = _now_iso()
        customer_id = str(uuid.uuid4())

        item = {
            "customer_id": customer_id,
            "first_name": body["first_name"],
            "last_name": body["last_name"],
            "email": body["email"],
            "created_at": now,
            "updated_at": now,
        }

        # Include optional phone field when provided
        if "phone" in body and body["phone"] is not None:
            item["phone"] = body["phone"]

        _table.put_item(Item=item)

        resource = _item_to_resource(item)
        return build_success_response(201, resource)

    except ClientError as exc:
        logger.error("DynamoDB ClientError in create_customer: %s", exc)
        return build_error_response(
            500,
            "internal_error",
            "An internal error occurred while creating the customer.",
            req_id,
        )


def get_customer(event: dict) -> dict:
    """Handle GET /v1/customers/{customer_id} — fetch a single customer by ID.

    Performs a DynamoDB ``get_item`` lookup by ``customer_id``.  Returns the
    customer wrapped in the RACSOCE single-resource envelope on success, or a
    404 error envelope when the record does not exist.

    Args:
        event: API Gateway proxy event containing ``pathParameters``.

    Returns:
        A Lambda proxy response dict with status 200, 404, or 500.
    """
    req_id = _request_id(event)
    customer_id = (event.get("pathParameters") or {}).get("customer_id")

    try:
        response = _table.get_item(Key={"customer_id": customer_id})
        item = response.get("Item")

        if item is None:
            return build_error_response(
                404,
                "resource_not_found",
                f"Customer '{customer_id}' not found.",
                req_id,
            )

        return build_success_response(200, _item_to_resource(item))

    except ClientError as exc:
        logger.error("DynamoDB ClientError in get_customer: %s", exc)
        return build_error_response(
            500,
            "internal_error",
            "An internal error occurred while retrieving the customer.",
            req_id,
        )


def update_customer(event: dict) -> dict:
    """Handle PUT /v1/customers/{customer_id} — replace a customer record.

    Validates the request body, checks the customer exists (404 if not),
    then overwrites the DynamoDB item preserving the original ``created_at``
    and setting ``updated_at`` to the current UTC time.  Returns the updated
    resource in the RACSOCE single-resource envelope.

    Args:
        event: API Gateway proxy event containing ``pathParameters`` and body.

    Returns:
        A Lambda proxy response dict with status 200, 400, 404, or 500.
    """
    req_id = _request_id(event)
    customer_id = (event.get("pathParameters") or {}).get("customer_id")

    try:
        body = parse_body(event)
        validate_customer_payload(body)
    except ValidationError as exc:
        return build_error_response(400, "validation_failed", exc.message, req_id)
    except InvalidRequestError as exc:
        return build_error_response(400, "invalid_request", exc.message, req_id)

    try:
        # Check existence and retrieve original created_at
        existing = _table.get_item(Key={"customer_id": customer_id}).get("Item")
        if existing is None:
            return build_error_response(
                404,
                "resource_not_found",
                f"Customer '{customer_id}' not found.",
                req_id,
            )

        now = _now_iso()
        item = {
            "customer_id": customer_id,
            "first_name": body["first_name"],
            "last_name": body["last_name"],
            "email": body["email"],
            "created_at": existing["created_at"],  # preserve original
            "updated_at": now,
        }

        if "phone" in body and body["phone"] is not None:
            item["phone"] = body["phone"]

        _table.put_item(Item=item)

        return build_success_response(200, _item_to_resource(item))

    except ClientError as exc:
        logger.error("DynamoDB ClientError in update_customer: %s", exc)
        return build_error_response(
            500,
            "internal_error",
            "An internal error occurred while updating the customer.",
            req_id,
        )


def delete_customer(event: dict) -> dict:
    """Handle DELETE /v1/customers/{customer_id} — remove a customer record.

    Uses a DynamoDB ``delete_item`` with a ``ConditionExpression`` to ensure
    the item exists before deletion.  Returns 204 with an empty body on
    success, or 404 when the customer does not exist.

    Args:
        event: API Gateway proxy event containing ``pathParameters``.

    Returns:
        A Lambda proxy response dict with status 204, 404, or 500.
    """
    req_id = _request_id(event)
    customer_id = (event.get("pathParameters") or {}).get("customer_id")

    try:
        _table.delete_item(
            Key={"customer_id": customer_id},
            ConditionExpression="attribute_exists(customer_id)",
        )
        return {"statusCode": 204, "headers": _HEADERS, "body": ""}

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "ConditionalCheckFailedException":
            return build_error_response(
                404,
                "resource_not_found",
                f"Customer '{customer_id}' not found.",
                req_id,
            )
        logger.error("DynamoDB ClientError in delete_customer: %s", exc)
        return build_error_response(
            500,
            "internal_error",
            "An internal error occurred while deleting the customer.",
            req_id,
        )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def lambda_handler(event: dict, context: object) -> dict:
    """Top-level Lambda entry point — route by HTTP method and path parameters.

    Routing table::

        GET    /v1/customers                → list_customers
        POST   /v1/customers                → create_customer
        GET    /v1/customers/{customer_id}  → get_customer
        PUT    /v1/customers/{customer_id}  → update_customer
        DELETE /v1/customers/{customer_id}  → delete_customer

    Args:
        event:   API Gateway proxy event dict.
        context: Lambda context object (unused directly).

    Returns:
        A Lambda proxy response dict.
    """
    try:
        method = event.get("httpMethod", "").upper()
        path_params = event.get("pathParameters") or {}
        has_customer_id = bool(path_params.get("customer_id"))

        if method == "GET" and not has_customer_id:
            return list_customers(event)

        if method == "POST" and not has_customer_id:
            return create_customer(event)

        if has_customer_id:
            if method == "GET":
                return get_customer(event)
            if method == "PUT":
                return update_customer(event)
            if method == "DELETE":
                return delete_customer(event)

        # Fallback for unrecognised routes
        return build_error_response(
            400,
            "invalid_request",
            f"Unsupported route: {method} with pathParameters={path_params}",
            _request_id(event),
        )

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled exception in lambda_handler: %s", exc, exc_info=True)
        return build_error_response(
            500,
            "internal_error",
            "An unexpected internal error occurred.",
            _request_id(event),
        )
