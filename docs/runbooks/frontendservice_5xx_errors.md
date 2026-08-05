# Incident: FrontendService 5xx Errors

## Description
Users are seeing 5xx errors on the storefront.

## Root Cause
Often triggered by failing downstream services like checkout or cart services.

## Remediation
1. Identify failing downstream dependency.
2. Restart the frontend deployment.
3. Check ingress configuration.
