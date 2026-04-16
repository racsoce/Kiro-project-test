# Copyright (c) RACSOCE. All rights reserved.

locals {
  common_tags = {
    Project     = "serverless-customer-platform"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── DynamoDB ──────────────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "customers" {
  name         = "customers-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "customer_id"

  attribute {
    name = "customer_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.common_tags
}

# ── Cognito ───────────────────────────────────────────────────────────────────

resource "aws_cognito_user_pool" "main" {
  name = "racsoce-customers-${var.environment}"

  tags = local.common_tags
}

resource "aws_cognito_user_pool_client" "api" {
  name         = "racsoce-customers-api-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  access_token_validity  = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    refresh_token = "days"
  }
}

# ── Lambda source archives ────────────────────────────────────────────────────

data "archive_file" "authorizer_zip" {
  type        = "zip"
  source_dir  = "../src/authorizer"
  output_path = "../.terraform/authorizer.zip"
}

data "archive_file" "customers_zip" {
  type        = "zip"
  source_dir  = "../src/users"
  output_path = "../.terraform/customers.zip"
}

# ── IAM — Authorizer Lambda ───────────────────────────────────────────────────

resource "aws_iam_role" "authorizer_lambda" {
  name = "authorizer-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "authorizer_basic_execution" {
  role       = aws_iam_role.authorizer_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── IAM — Customers Lambda ────────────────────────────────────────────────────

resource "aws_iam_role" "customers_lambda" {
  name = "customers-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "customers_basic_execution" {
  role       = aws_iam_role.customers_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "customers_dynamodb" {
  name = "customers-dynamodb-${var.environment}"
  role = aws_iam_role.customers_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.customers.arn
      }
    ]
  })
}

# ── Lambda Functions ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "authorizer" {
  function_name    = "authorizer-${var.environment}"
  filename         = data.archive_file.authorizer_zip.output_path
  source_code_hash = data.archive_file.authorizer_zip.output_base64sha256
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  role             = aws_iam_role.authorizer_lambda.arn

  environment {
    variables = {
      COGNITO_USER_POOL_ID    = aws_cognito_user_pool.main.id
      COGNITO_APP_CLIENT_ID   = aws_cognito_user_pool_client.api.id
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "customers" {
  function_name    = "customers-${var.environment}"
  filename         = data.archive_file.customers_zip.output_path
  source_code_hash = data.archive_file.customers_zip.output_base64sha256
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  role             = aws_iam_role.customers_lambda.arn

  environment {
    variables = {
      COGNITO_USER_POOL_ID    = aws_cognito_user_pool.main.id
      COGNITO_APP_CLIENT_ID   = aws_cognito_user_pool_client.api.id
      DYNAMODB_TABLE_NAME     = aws_dynamodb_table.customers.name
    }
  }

  tags = local.common_tags
}

# ── Lambda Permissions — API Gateway invocation ───────────────────────────────

resource "aws_lambda_permission" "authorizer_apigw" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "customers_apigw" {
  statement_id  = "AllowAPIGatewayInvokeCustomers"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.customers.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# ── API Gateway — REST API ────────────────────────────────────────────────────

resource "aws_api_gateway_rest_api" "main" {
  name        = "racsoce-customers-${var.environment}"
  description = "RACSOCE Serverless Customer Platform API"

  tags = local.common_tags
}

# ── API Gateway — Lambda Authorizer ──────────────────────────────────────────

resource "aws_api_gateway_authorizer" "cognito_jwt" {
  name                             = "cognito-jwt-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.main.id
  type                             = "TOKEN"
  authorizer_uri                   = aws_lambda_function.authorizer.invoke_arn
  identity_source                  = "method.request.header.Authorization"
  authorizer_result_ttl_in_seconds = 300
}

# ── API Gateway — Resources ───────────────────────────────────────────────────

resource "aws_api_gateway_resource" "v1" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "v1"
}

resource "aws_api_gateway_resource" "customers" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "customers"
}

resource "aws_api_gateway_resource" "customer_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.customers.id
  path_part   = "{customer_id}"
}

# ── API Gateway — GET /v1/customers ──────────────────────────────────────────

resource "aws_api_gateway_method" "list_customers" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customers.id
  http_method   = "GET"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.cognito_jwt.id
}

resource "aws_api_gateway_integration" "list_customers" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.customers.id
  http_method             = aws_api_gateway_method.list_customers.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.customers.invoke_arn
}

# ── API Gateway — POST /v1/customers ─────────────────────────────────────────

resource "aws_api_gateway_method" "create_customer" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customers.id
  http_method   = "POST"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.cognito_jwt.id
}

resource "aws_api_gateway_integration" "create_customer" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.customers.id
  http_method             = aws_api_gateway_method.create_customer.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.customers.invoke_arn
}

# ── API Gateway — GET /v1/customers/{customer_id} ────────────────────────────

resource "aws_api_gateway_method" "get_customer" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customer_id.id
  http_method   = "GET"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.cognito_jwt.id
}

resource "aws_api_gateway_integration" "get_customer" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.customer_id.id
  http_method             = aws_api_gateway_method.get_customer.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.customers.invoke_arn
}

# ── API Gateway — PUT /v1/customers/{customer_id} ────────────────────────────

resource "aws_api_gateway_method" "update_customer" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customer_id.id
  http_method   = "PUT"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.cognito_jwt.id
}

resource "aws_api_gateway_integration" "update_customer" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.customer_id.id
  http_method             = aws_api_gateway_method.update_customer.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.customers.invoke_arn
}

# ── API Gateway — DELETE /v1/customers/{customer_id} ─────────────────────────

resource "aws_api_gateway_method" "delete_customer" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customer_id.id
  http_method   = "DELETE"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.cognito_jwt.id
}

resource "aws_api_gateway_integration" "delete_customer" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.customer_id.id
  http_method             = aws_api_gateway_method.delete_customer.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.customers.invoke_arn
}

# ── API Gateway — CORS: OPTIONS /v1/customers ─────────────────────────────────

resource "aws_api_gateway_method" "options_customers" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customers.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_customers" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customers.id
  http_method = aws_api_gateway_method.options_customers.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_customers_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customers.id
  http_method = aws_api_gateway_method.options_customers.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options_customers_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customers.id
  http_method = aws_api_gateway_method.options_customers.http_method
  status_code = aws_api_gateway_method_response.options_customers_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.options_customers]
}

# ── API Gateway — CORS: OPTIONS /v1/customers/{customer_id} ──────────────────

resource "aws_api_gateway_method" "options_customer_id" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.customer_id.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_customer_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customer_id.id
  http_method = aws_api_gateway_method.options_customer_id.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_customer_id_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customer_id.id
  http_method = aws_api_gateway_method.options_customer_id.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options_customer_id_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.customer_id.id
  http_method = aws_api_gateway_method.options_customer_id.http_method
  status_code = aws_api_gateway_method_response.options_customer_id_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,PUT,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.options_customer_id]
}

# ── API Gateway — Deployment & Stage ─────────────────────────────────────────

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  depends_on = [
    aws_api_gateway_integration.list_customers,
    aws_api_gateway_integration.create_customer,
    aws_api_gateway_integration.get_customer,
    aws_api_gateway_integration.update_customer,
    aws_api_gateway_integration.delete_customer,
    aws_api_gateway_integration.options_customers,
    aws_api_gateway_integration.options_customer_id,
  ]
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = "v1"

  tags = local.common_tags
}
