# Implementation Plan: Serverless Customer Platform

## Overview

Implement the RACSOCE MVP serverless customer management platform incrementally: project scaffolding and shared utilities first, then the Lambda Authorizer, then the Customers Lambda with full CRUD, and finally the Terraform infrastructure that wires everything together. Unit and property-based tests are co-located with each component so correctness is validated as each piece is built.

## Tasks

- [x] 1. Scaffold project structure and shared utilities
  - Create directory tree: `src/authorizer/`, `src/users/`, `tests/unit/events/`, `tests/integration/`, `infra/envs/`
  - Add `src/authorizer/requirements.txt` (`boto3`, `python-jose`)
  - Add `src/users/requirements.txt` (`boto3`)
  - Add root `requirements-dev.txt` (`pytest`, `hypothesis`, `moto`, `pytest-mock`)
  - Create `src/shared/response.py` with `build_success_response`, `build_error_response`, and `build_collection_response` helpers that produce the RACSOCE JSON envelope (`data` / `error` wrappers, snake_case, ISO 8601 dates)
  - Add copyright header to every source file
  - _Requirements: REST API endpoints (API.1)_

- [x] 2. Implement the Lambda Authorizer
  - [x] 2.1 Implement `src/authorizer/lambda_function.py`
    - Extract Bearer JWT from `authorizationToken`
    - Fetch and in-memory cache Cognito JWKS public keys
    - Verify JWT signature, `exp`, and `aud` claims using `python-jose`
    - Return `Allow` IAM policy with `principalId` and `context.user_id` on success
    - Raise `Exception("Unauthorized")` for any invalid token (expired, bad signature, malformed)
    - Wrap top-level logic in `try/except`; log errors to CloudWatch
    - Add copyright header
    - _Requirements: User authentication with Cognito (Auth.1, Auth.2, Auth.3)_

  - [ ]* 2.2 Write property test for invalid JWT rejection (Property 1)
    - **Property 1: Invalid JWT is always rejected**
    - **Validates: Requirements Auth.2, Auth.3**
    - Use `hypothesis` with `@settings(max_examples=100)`
    - Generate: expired JWTs (past `exp`), JWTs signed with a wrong key, structurally malformed strings
    - Assert authorizer returns Deny policy for every generated token
    - Tag: `# Feature: serverless-customer-platform, Property 1: Invalid JWT is always rejected`
    - Place in `tests/unit/test_authorizer_properties.py`

  - [ ]* 2.3 Write unit tests for the Lambda Authorizer
    - Valid token → Allow policy with correct `principalId`
    - Expired token → Deny / raises Unauthorized
    - Wrong-key token → Deny / raises Unauthorized
    - Malformed string → Deny / raises Unauthorized
    - Missing `Authorization` header → raises Unauthorized
    - Place in `tests/unit/test_authorizer.py`; use `unittest.mock` to mock JWKS fetch
    - _Requirements: Auth.1, Auth.2, Auth.3_

- [x] 3. Checkpoint — Authorizer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement input validation and DynamoDB helpers for the Customers Lambda
  - [x] 4.1 Create `src/users/validation.py`
    - `validate_customer_payload(body: dict) -> None` — raises `ValidationError` if `first_name`, `last_name`, or `email` is missing or if `email` does not match a valid email regex
    - `parse_body(event: dict) -> dict` — parses JSON body; raises `InvalidRequestError` on malformed JSON
    - Add copyright header
    - _Requirements: Basic CRUD operations (CRUD.2, CRUD.3)_

  - [ ]* 4.2 Write property test for invalid payload rejection (Property 3)
    - **Property 3: Invalid payload is always rejected**
    - **Validates: Requirements CRUD.2, CRUD.3**
    - Use `hypothesis` with `@settings(max_examples=100)`
    - Generate payloads with one or more required fields removed, or with non-email strings in `email`
    - Assert `validate_customer_payload` raises `ValidationError` for every generated invalid payload
    - Assert valid payloads never raise
    - Tag: `# Feature: serverless-customer-platform, Property 3: Invalid payload is always rejected`
    - Place in `tests/unit/test_validation_properties.py`

  - [ ]* 4.3 Write unit tests for validation helpers
    - Missing `first_name` → `ValidationError`
    - Missing `last_name` → `ValidationError`
    - Missing `email` → `ValidationError`
    - Invalid email format → `ValidationError`
    - Malformed JSON body → `InvalidRequestError`
    - All required fields present with valid email → no error
    - Place in `tests/unit/test_validation.py`
    - _Requirements: CRUD.2, CRUD.3_

- [x] 5. Implement the Customers Lambda CRUD handler
  - [x] 5.1 Implement `src/users/lambda_function.py` — router and List / Create operations
    - Top-level `lambda_handler` routes by `httpMethod` and presence of `pathParameters`
    - `list_customers`: scan DynamoDB, return collection envelope with `meta.total`
    - `create_customer`: validate payload, generate UUID v4 `customer_id`, set `created_at` / `updated_at` (ISO 8601 UTC), write to DynamoDB, return 201 with single-resource envelope
    - Wrap all handlers in `try/except`; map `ClientError` to 500; return RACSOCE error envelope
    - Add copyright header
    - _Requirements: CRUD.1, CRUD.2, CRUD.3, API.1_

  - [ ]* 5.2 Write property test for customer creation round-trip (Property 2)
    - **Property 2: Customer creation round-trip**
    - **Validates: Requirements CRUD.1, CRUD.4**
    - Use `hypothesis` with `@settings(max_examples=100)`; mock DynamoDB with `moto`
    - Generate random valid payloads (`st.text(min_size=1)` for names, `st.emails()` for email)
    - POST → assert 201 and `customer_id` present; GET by returned ID → assert attributes match payload
    - Tag: `# Feature: serverless-customer-platform, Property 2: Customer creation round-trip`
    - Place in `tests/unit/test_customers_properties.py`

  - [x] 5.3 Implement Get / Update / Delete operations in `src/users/lambda_function.py`
    - `get_customer`: fetch by `customer_id`; return 200 with single-resource envelope or 404 error envelope
    - `update_customer`: validate payload, overwrite item in DynamoDB preserving `created_at`, update `updated_at`, return 200 with updated envelope
    - `delete_customer`: delete item by `customer_id`; return 204 (no body); return 404 if item not found
    - _Requirements: CRUD.4, CRUD.5, CRUD.6, CRUD.7_

  - [ ]* 5.4 Write property test for non-existent customer 404 (Property 4)
    - **Property 4: Non-existent customer always returns 404**
    - **Validates: Requirements CRUD.5**
    - Use `hypothesis` with `@settings(max_examples=100)`; mock DynamoDB with `moto`
    - Generate random UUIDs not present in the table; GET; assert 404 and error envelope
    - Tag: `# Feature: serverless-customer-platform, Property 4: Non-existent customer always returns 404`
    - Place in `tests/unit/test_customers_properties.py`

  - [ ]* 5.5 Write property test for customer update round-trip (Property 5)
    - **Property 5: Customer update round-trip**
    - **Validates: Requirements CRUD.6**
    - Use `hypothesis` with `@settings(max_examples=100)`; mock DynamoDB with `moto`
    - Create a customer; generate replacement payload; PUT; GET; assert attributes match replacement and `updated_at` > original `updated_at`
    - Tag: `# Feature: serverless-customer-platform, Property 5: Customer update round-trip`
    - Place in `tests/unit/test_customers_properties.py`

  - [ ]* 5.6 Write property test for deleted customer not retrievable (Property 6)
    - **Property 6: Deleted customer is not retrievable**
    - **Validates: Requirements CRUD.7**
    - Use `hypothesis` with `@settings(max_examples=100)`; mock DynamoDB with `moto`
    - Create a customer; DELETE (assert 204); GET; assert 404
    - Tag: `# Feature: serverless-customer-platform, Property 6: Deleted customer is not retrievable`
    - Place in `tests/unit/test_customers_properties.py`

  - [ ]* 5.7 Write property test for RACSOCE envelope conformance (Property 7)
    - **Property 7: Every success response conforms to the RACSOCE envelope**
    - **Validates: Requirements API.1**
    - Use `hypothesis` with `@settings(max_examples=100)`; mock DynamoDB with `moto`
    - For any successful operation (list, create, get, update), assert response body has `data` key; single-resource responses have `id`, `type`, `attributes`; collection responses have array `data` and `meta.total`; all date fields parse as ISO 8601; all field names are snake_case
    - Tag: `# Feature: serverless-customer-platform, Property 7: Every success response conforms to the RACSOCE envelope`
    - Place in `tests/unit/test_customers_properties.py`

  - [ ]* 5.8 Write unit tests for the Customers Lambda
    - Store representative API Gateway proxy event JSON fixtures in `tests/unit/events/` (one per operation)
    - Test each route: list, create, get, update, delete — happy path and error cases
    - Verify 404 for unknown `customer_id`
    - Verify 400 for missing required fields (no DynamoDB write via mock assertion)
    - Verify 500 on DynamoDB `ClientError`
    - Place in `tests/unit/test_customers.py`; use `moto` or `unittest.mock`
    - _Requirements: CRUD.1–CRUD.7, API.1_

- [x] 6. Checkpoint — All unit and property tests pass
  - Ensure all tests pass (`pytest tests/unit/`), ask the user if questions arise.

- [x] 7. Write Terraform infrastructure
  - [x] 7.1 Create `infra/providers.tf` and `infra/versions.tf`
    - Pin AWS provider version; set default region to `us-east-1`
    - _Requirements: REST API endpoints (API.1)_

  - [x] 7.2 Create `infra/variables.tf` and `infra/terraform.tfvars`
    - Declare variables: `environment`, `aws_region`, `cognito_user_pool_id`, `cognito_app_client_id`
    - Populate `terraform.tfvars` with dev defaults
    - Create `infra/envs/dev.tfvars` and `infra/envs/prod.tfvars`
    - _Requirements: User authentication with Cognito (Auth.1)_

  - [x] 7.3 Create `infra/main.tf` — DynamoDB table
    - `aws_dynamodb_table` resource: `customers`, partition key `customer_id` (String), on-demand billing, point-in-time recovery enabled
    - _Requirements: Basic CRUD operations (CRUD.1)_

  - [x] 7.4 Create `infra/main.tf` — Cognito User Pool and App Client
    - `aws_cognito_user_pool` resource with access token validity 1 hour, refresh token 30 days
    - `aws_cognito_user_pool_client` resource (no hosted UI)
    - _Requirements: User authentication with Cognito (Auth.1)_

  - [x] 7.5 Create `infra/main.tf` — Lambda functions and IAM roles
    - IAM execution roles for authorizer and customers Lambda with least-privilege policies (DynamoDB read/write for customers Lambda; no DynamoDB access for authorizer)
    - `aws_lambda_function` for `src/authorizer/` and `src/users/` with environment variables (`COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `DYNAMODB_TABLE_NAME`)
    - _Requirements: User authentication with Cognito (Auth.1), Basic CRUD operations (CRUD.1)_

  - [x] 7.6 Create `infra/main.tf` — API Gateway REST API, routes, and authorizer
    - `aws_api_gateway_rest_api` with stage `v1`
    - TOKEN Lambda Authorizer wired to all methods (`Authorization` header)
    - Resources and methods for all 5 routes: `GET /v1/customers`, `POST /v1/customers`, `GET /v1/customers/{customer_id}`, `PUT /v1/customers/{customer_id}`, `DELETE /v1/customers/{customer_id}`
    - Lambda proxy integration for all methods
    - CORS enabled
    - _Requirements: REST API endpoints (API.1), User authentication with Cognito (Auth.1)_

  - [x] 7.7 Create `infra/outputs.tf`
    - Output: `api_gateway_invoke_url`, `cognito_user_pool_id`, `cognito_app_client_id`, `dynamodb_table_name`
    - _Requirements: REST API endpoints (API.1)_

- [x] 8. Validate Terraform configuration
  - Run `terraform init` and `terraform validate` against the `infra/` directory
  - Fix any syntax or schema errors reported
  - _Requirements: REST API endpoints (API.1)_

- [ ] 9. Write integration tests
  - [ ]* 9.1 Write integration tests in `tests/integration/`
    - Authenticate against Cognito to obtain a real JWT
    - Test each CRUD endpoint against a deployed dev environment: assert HTTP status codes and response envelope shapes
    - Verify unauthenticated requests receive 401
    - Verify deleted customer returns 404 on subsequent GET
    - Place in `tests/integration/test_customers_integration.py`
    - Add copyright header
    - _Requirements: Auth.1, Auth.2, CRUD.1–CRUD.7, API.1_

- [x] 10. Final checkpoint — All tests pass
  - Ensure all tests pass (`pytest tests/unit/`), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP delivery
- All source files must include the RACSOCE copyright header (see `tech.md`)
- Property tests use `hypothesis` with `@settings(max_examples=100)` and are tagged with the format `# Feature: serverless-customer-platform, Property <N>: <text>`
- Unit tests mock AWS services with `moto` or `unittest.mock`; no real AWS credentials are required for unit tests
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation before moving to the next phase
