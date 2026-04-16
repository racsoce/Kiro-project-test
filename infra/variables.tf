# Copyright (c) RACSOCE. All rights reserved.

variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, prod)"
  type        = string
  default     = "dev"
}

variable "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool used for JWT authentication"
  type        = string
}

variable "cognito_app_client_id" {
  description = "App client ID of the Cognito User Pool client"
  type        = string
}
