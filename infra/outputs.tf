# Copyright (c) RACSOCE. All rights reserved.

output "api_gateway_invoke_url" {
  description = "Full invoke URL for the v1 stage of the API Gateway REST API"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_app_client_id" {
  description = "App client ID of the Cognito User Pool client"
  value       = aws_cognito_user_pool_client.api.id
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB customers table"
  value       = aws_dynamodb_table.customers.name
}
