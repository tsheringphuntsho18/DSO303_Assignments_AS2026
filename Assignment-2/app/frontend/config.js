// Fill these in from `terraform output` after `terraform apply` (see
// ../../README.md "Deploy" section). Left blank here so the repo doesn't
// carry any account-specific values.
window.EDUEXAM_CONFIG = {
  apiBaseUrl: "", // e.g. "https://d111111abcdef8.cloudfront.net/api" or the raw api_invoke_url output
  cognito: {
    userPoolId: "", // output: cognito_user_pool_id
    clientId: "", // output: cognito_app_client_id
    region: "us-east-1",
  },
};
