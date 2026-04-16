# Copyright (c) RACSOCE. All rights reserved.
"""
Lambda Authorizer for the RACSOCE serverless customer platform.

Validates Cognito-issued JWTs presented as Bearer tokens in the
``authorizationToken`` field of the API Gateway TOKEN authorizer event.
On success, returns an IAM ``Allow`` policy with the Cognito ``sub`` claim
set as both ``principalId`` and ``context.user_id``.
On failure, raises ``Exception("Unauthorized")`` so API Gateway returns 401.

Environment variables:
    COGNITO_USER_POOL_ID  – Cognito User Pool ID (e.g. ``us-east-1_Abc123``)
    COGNITO_APP_CLIENT_ID – Cognito App Client ID (used as the ``aud`` claim)
    AWS_REGION            – AWS region (injected automatically by Lambda)
"""

import json
import logging
import os
import urllib.request

from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Module-level JWKS cache — populated once per Lambda container lifetime
# ---------------------------------------------------------------------------

_JWKS_CACHE = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_jwks(region: str, user_pool_id: str) -> dict:
    """Fetch Cognito JWKS, using the module-level cache after the first call.

    Args:
        region: AWS region where the User Pool lives.
        user_pool_id: Cognito User Pool ID.

    Returns:
        The parsed JWKS JSON document (dict with a ``keys`` list).
    """
    global _JWKS_CACHE  # noqa: PLW0603

    if _JWKS_CACHE is not None:
        logger.info("Returning cached JWKS")
        return _JWKS_CACHE

    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com"
        f"/{user_pool_id}/.well-known/jwks.json"
    )
    logger.info("Fetching JWKS from %s", jwks_url)

    with urllib.request.urlopen(jwks_url) as response:  # noqa: S310
        _JWKS_CACHE = json.loads(response.read().decode("utf-8"))

    return _JWKS_CACHE


def _build_allow_policy(principal_id: str, method_arn: str) -> dict:
    """Build an IAM ``Allow`` policy document for API Gateway.

    Args:
        principal_id: The Cognito ``sub`` claim to use as the principal.
        method_arn: The ``methodArn`` from the authorizer event.

    Returns:
        A dict representing the authorizer response with policy and context.
    """
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": method_arn,
                }
            ],
        },
        "context": {
            "user_id": principal_id,
        },
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    """API Gateway TOKEN Lambda Authorizer entry point.

    Extracts the Bearer JWT from ``event["authorizationToken"]``, verifies it
    against the Cognito JWKS endpoint, and returns an ``Allow`` IAM policy on
    success.  Any failure raises ``Exception("Unauthorized")``.

    Args:
        event: API Gateway authorizer event containing ``authorizationToken``
               and ``methodArn``.
        context: Lambda context object (unused).

    Returns:
        IAM policy document dict on successful verification.

    Raises:
        Exception: ``"Unauthorized"`` for any invalid, expired, or malformed
                   token, or if required environment variables are missing.
    """
    try:
        region = os.environ["AWS_REGION"]
        user_pool_id = os.environ["COGNITO_USER_POOL_ID"]
        app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]

        # ------------------------------------------------------------------ #
        # 1. Extract the Bearer token
        # ------------------------------------------------------------------ #
        auth_header: str = event.get("authorizationToken", "")
        if not auth_header.lower().startswith("bearer "):
            logger.warning("authorizationToken is missing or not a Bearer token")
            raise Exception("Unauthorized")  # noqa: TRY301

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            logger.warning("Bearer token is empty")
            raise Exception("Unauthorized")  # noqa: TRY301

        # ------------------------------------------------------------------ #
        # 2. Fetch (or retrieve from cache) the Cognito JWKS
        # ------------------------------------------------------------------ #
        jwks = _get_jwks(region, user_pool_id)

        # ------------------------------------------------------------------ #
        # 3. Verify the JWT — signature, exp, and aud
        # ------------------------------------------------------------------ #
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=app_client_id,
        )

        # ------------------------------------------------------------------ #
        # 4. Build and return the Allow policy
        # ------------------------------------------------------------------ #
        principal_id: str = claims["sub"]
        method_arn: str = event.get("methodArn", "*")

        logger.info("Token verified for principal %s", principal_id)
        return _build_allow_policy(principal_id, method_arn)

    except Exception as exc:
        # Re-raise "Unauthorized" as-is so API Gateway returns 401.
        # Log any unexpected error before converting it.
        if str(exc) == "Unauthorized":
            raise

        logger.error("Token verification failed: %s", exc, exc_info=True)
        raise Exception("Unauthorized") from exc  # noqa: TRY301
