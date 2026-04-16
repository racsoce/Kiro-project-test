# Copyright (c) RACSOCE. All rights reserved.
"""
Input validation helpers for the Customers Lambda.

Provides payload validation and JSON body parsing with descriptive
custom exceptions that map cleanly to RACSOCE error envelope codes.
"""

import json
import re

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

_REQUIRED_FIELDS = ("first_name", "last_name", "email")


class ValidationError(Exception):
    """Raised when a customer payload fails field-level validation.

    Attributes:
        message: Human-readable description of the validation failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequestError(Exception):
    """Raised when the request body cannot be parsed as valid JSON.

    Attributes:
        message: Human-readable description of the parse failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def validate_customer_payload(body: dict) -> None:
    """Validate that a customer payload contains all required fields.

    Checks that ``first_name``, ``last_name``, and ``email`` are present
    and that ``email`` matches a standard email format.

    Args:
        body: Parsed request body as a dictionary.

    Raises:
        ValidationError: If any required field is missing or if ``email``
            does not match the expected format.
    """
    for field in _REQUIRED_FIELDS:
        if field not in body or body[field] is None:
            raise ValidationError(f"Missing required field: '{field}'")

    if not EMAIL_REGEX.match(str(body["email"])):
        raise ValidationError(
            f"Invalid email format: '{body['email']}'"
        )


def parse_body(event: dict) -> dict:
    """Parse the JSON body from an API Gateway proxy event.

    Args:
        event: The raw API Gateway proxy event dictionary.

    Returns:
        The parsed request body as a dictionary.

    Raises:
        InvalidRequestError: If ``event["body"]`` is absent, ``None``,
            or contains malformed JSON.
    """
    raw = event.get("body")
    if raw is None:
        raise InvalidRequestError("Request body is missing")

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise InvalidRequestError("Request body contains malformed JSON")

    if not isinstance(parsed, dict):
        raise InvalidRequestError("Request body must be a JSON object")

    return parsed
