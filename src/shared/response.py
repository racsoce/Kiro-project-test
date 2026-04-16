# Copyright (c) RACSOCE. All rights reserved.
"""
Shared response helpers that produce RACSOCE JSON API envelopes.

All Lambda handlers should use these helpers to ensure consistent
response shapes, headers, and serialisation across the platform.
"""

import json

# ---------------------------------------------------------------------------
# Common headers
# ---------------------------------------------------------------------------

_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_success_response(status_code: int, data: dict) -> dict:
    """Return a full Lambda proxy response for a single-resource success.

    The body is serialised to a JSON string following the RACSOCE envelope::

        { "data": { "id": "...", "type": "...", "attributes": { ... } } }

    Args:
        status_code: HTTP status code (e.g. 200, 201).
        data: The resource object to place under the ``data`` key.
              Typically a dict with ``id``, ``type``, and ``attributes``.

    Returns:
        A dict suitable for returning directly from a Lambda handler.
    """
    body = {"data": data}
    return {
        "statusCode": status_code,
        "headers": _HEADERS,
        "body": json.dumps(body),
    }


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
) -> dict:
    """Return a full Lambda proxy response for an error.

    The body follows the RACSOCE error envelope::

        {
            "error": {
                "code": "<error_code>",
                "message": "<human-readable message>",
                "request_id": "<api-gateway-request-id>"
            }
        }

    Args:
        status_code: HTTP status code (e.g. 400, 404, 500).
        code: Machine-readable error code (e.g. ``"validation_failed"``).
        message: Human-readable description of the error.
        request_id: Optional API Gateway request ID for correlation.

    Returns:
        A dict suitable for returning directly from a Lambda handler.
    """
    error_body: dict = {"code": code, "message": message}
    if request_id is not None:
        error_body["request_id"] = request_id

    body = {"error": error_body}
    return {
        "statusCode": status_code,
        "headers": _HEADERS,
        "body": json.dumps(body),
    }


def build_collection_response(items: list, total: int) -> dict:
    """Return the RACSOCE collection envelope body dict (not a full Lambda response).

    The returned dict follows the collection envelope::

        {
            "data": [ { "id": "...", "type": "...", "attributes": { ... } } ],
            "meta": { "total": 42 }
        }

    Callers are responsible for wrapping this in a Lambda proxy response, e.g.::

        envelope = build_collection_response(items, total)
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps(envelope),
        }

    Args:
        items: List of resource objects (each with ``id``, ``type``, ``attributes``).
        total: Total number of items in the collection (for pagination metadata).

    Returns:
        A dict with ``data`` and ``meta`` keys — not a full Lambda response.
    """
    return {
        "data": items,
        "meta": {"total": total},
    }
