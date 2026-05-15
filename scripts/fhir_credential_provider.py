#!/usr/bin/python
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
FHIR OBO (On-Behalf-Of) Credential Provider for AgentCore Identity.

Creates an OAuth2 credential provider configured for On-Behalf-Of token exchange.
This enables the agent to exchange the inbound user JWT for a scoped token
targeting the FHIR resource server.

Flow:
  1. User authenticates → Cognito issues JWT (inbound token)
  2. AgentCore Runtime validates the JWT (Inbound JWT Authorizer)
  3. Agent calls GetWorkloadAccessTokenForJWT (wraps user identity)
  4. Agent calls GetResourceOauth2Token with ON_BEHALF_OF_TOKEN_EXCHANGE
  5. AgentCore Identity brokers the exchange with Cognito's token endpoint
  6. Agent receives a scoped OBO token for the FHIR resource server
  7. Agent passes OBO token to FHIR API Gateway → Lambda validates it

The OBO token carries both the agent's identity and the user's identity,
enabling the FHIR service to enforce fine-grained authorization.
"""

import sys
import boto3
import click
from botocore.exceptions import ClientError

sys.path.insert(0, "scripts")
from utils import get_ssm_parameter, put_ssm_parameter, delete_ssm_parameter, get_aws_region

REGION = get_aws_region()

identity_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=REGION,
)

PROVIDER_NAME = "healthcare-fhir-obo-provider"
SSM_PROVIDER_NAME = "/app/healthcare/fhir/obo_provider_name"
WORKLOAD_IDENTITY_NAME = "healthcare_premium"


def ensure_workload_identity() -> str:
    """
    Create the workload identity required for OBO token exchange.

    GetWorkloadAccessTokenForJWT requires a workload identity in the same
    account as the agent runtime. Without this, the OBO flow fails with:
    "Workload Identity does not belong to caller account"
    """
    try:
        click.echo(f"⚙️  Ensuring workload identity '{WORKLOAD_IDENTITY_NAME}' exists...")
        response = identity_client.create_workload_identity(
            name=WORKLOAD_IDENTITY_NAME,
        )
        click.echo(f"✅ Created workload identity: {WORKLOAD_IDENTITY_NAME}")
        click.echo(f"   ARN: {response.get('workloadIdentityArn', 'N/A')}")
    except identity_client.exceptions.ConflictException:
        click.echo(f"ℹ️  Workload identity '{WORKLOAD_IDENTITY_NAME}' already exists")
    except Exception as e:
        click.echo(f"❌ Failed to create workload identity: {e}", err=True)
        sys.exit(1)
    return WORKLOAD_IDENTITY_NAME


def create_fhir_obo_provider() -> dict:
    """
    Create an OAuth2 credential provider with OBO token exchange config.

    Uses Cognito as both the authorization server and the resource server.
    The TOKEN_EXCHANGE grant type with NONE actor token is used because
    Cognito doesn't require a separate actor token for the exchange.
    """
    try:
        click.echo("📥 Fetching Cognito configuration from SSM...")

        # Use the same Cognito pool — it's both the IdP and the resource server
        client_id = get_ssm_parameter("/app/healthcare/agentcore/machine_client_id")
        client_secret = get_ssm_parameter("/app/healthcare/agentcore/cognito_secret")
        issuer = get_ssm_parameter("/app/healthcare/agentcore/cognito_discovery_url")
        token_url = get_ssm_parameter("/app/healthcare/agentcore/cognito_token_url")
        auth_url = get_ssm_parameter("/app/healthcare/agentcore/cognito_auth_url")

        click.echo(f"✅ Client ID: {client_id}")
        click.echo(f"✅ Issuer: {issuer}")
        click.echo(f"✅ Token Endpoint: {token_url}")

        click.echo("⚙️  Creating FHIR OBO credential provider...")

        response = identity_client.create_oauth2_credential_provider(
            name=PROVIDER_NAME,
            credentialProviderVendor="CustomOauth2",
            oauth2ProviderConfigInput={
                "customOauth2ProviderConfig": {
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "clientAuthenticationMethod": "CLIENT_SECRET_BASIC",
                    "oauthDiscovery": {
                        "authorizationServerMetadata": {
                            "issuer": issuer,
                            "authorizationEndpoint": auth_url,
                            "tokenEndpoint": token_url,
                            "responseTypes": ["code", "token"],
                        }
                    },
                    "onBehalfOfTokenExchangeConfig": {
                        "grantType": "TOKEN_EXCHANGE",
                        "tokenExchangeGrantTypeConfig": {
                            "actorTokenContent": "NONE",
                        },
                    },
                }
            },
        )

        provider_arn = response["credentialProviderArn"]
        click.echo(f"✅ FHIR OBO credential provider created")
        click.echo(f"   Provider ARN: {provider_arn}")
        click.echo(f"   Provider Name: {response['name']}")

        # Store in SSM
        put_ssm_parameter(SSM_PROVIDER_NAME, PROVIDER_NAME)
        click.echo(f"🔐 Stored provider name in SSM: {SSM_PROVIDER_NAME}")

        return response

    except (identity_client.exceptions.ConflictException, ClientError) as e:
        error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        error_msg = str(e)
        if "already exists" in error_msg.lower() or error_code in ("ConflictException", "ValidationException"):
            click.echo(f"ℹ️  Provider '{PROVIDER_NAME}' already exists")
            put_ssm_parameter(SSM_PROVIDER_NAME, PROVIDER_NAME)
            return {"name": PROVIDER_NAME}
        click.echo(f"❌ Error creating FHIR OBO provider: {error_msg}", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Error creating FHIR OBO provider: {str(e)}", err=True)
        sys.exit(1)


def delete_fhir_obo_provider():
    """Delete the FHIR OBO credential provider and workload identity."""
    try:
        click.echo(f"🗑️  Deleting FHIR OBO credential provider: {PROVIDER_NAME}")
        identity_client.delete_oauth2_credential_provider(name=PROVIDER_NAME)
        click.echo("✅ Provider deleted")
        delete_ssm_parameter(SSM_PROVIDER_NAME)
    except Exception as e:
        click.echo(f"⚠️  Could not delete provider: {e}")

    try:
        click.echo(f"🗑️  Deleting workload identity: {WORKLOAD_IDENTITY_NAME}")
        identity_client.delete_workload_identity(name=WORKLOAD_IDENTITY_NAME)
        click.echo("✅ Workload identity deleted")
    except Exception as e:
        click.echo(f"⚠️  Could not delete workload identity: {e}")


@click.group()
def cli():
    """FHIR OBO Credential Provider Management."""
    pass


@cli.command()
def create():
    """Create the FHIR OBO credential provider."""
    click.echo(f"🚀 Creating FHIR OBO credential provider")
    click.echo(f"📍 Region: {REGION}")
    ensure_workload_identity()
    create_fhir_obo_provider()
    click.echo("🎉 Done!")


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(confirm):
    """Delete the FHIR OBO credential provider."""
    if not confirm:
        if not click.confirm("⚠️  Delete the FHIR OBO credential provider?"):
            click.echo("❌ Cancelled")
            return
    delete_fhir_obo_provider()


if __name__ == "__main__":
    cli()
