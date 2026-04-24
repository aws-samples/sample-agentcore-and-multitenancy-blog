#!/usr/bin/env python3
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Create Bedrock Projects for multi-tenant cost attribution via the Mantle endpoint.

This script replaces create_inference_profiles.py. Instead of application inference
profiles (which use the bedrock-runtime endpoint), it creates Bedrock Projects that
work with the Mantle (OpenAI-compatible) endpoint for cost tracking in AWS Cost Explorer.

Each tier gets a dedicated project with tags for Application, Tier, Environment,
and CostCenter. The project IDs are stored in SSM Parameter Store so the agent
can load them at runtime.

Prerequisites:
  - IAM permissions: AmazonBedrockMantleFullAccess (or equivalent project management)
"""

import os
import sys
import requests

# Allow running from project root: python -m scripts.create_bedrock_projects
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.utils import get_ssm_parameter, put_ssm_parameter, get_aws_region


# --- Tier definitions ---

TIER_PROJECTS = {
    "basic": {
        "name": "Healthcare-Basic",
        "tags": {
            "Application": "HealthcareDemo",
            "Tier": "Basic",
            "Environment": "demo",
            "CostCenter": "HC-Basic",
        },
        "ssm_param": "/app/healthcare/projects/basic_id",
    },
    "premium": {
        "name": "Healthcare-Premium",
        "tags": {
            "Application": "HealthcareDemo",
            "Tier": "Premium",
            "Environment": "demo",
            "CostCenter": "HC-Premium",
        },
        "ssm_param": "/app/healthcare/projects/premium_id",
    },
}


def _mantle_base_url(region: str) -> str:
    return f"https://bedrock-mantle.{region}.api.aws/v1"


def _auth_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def list_projects(base_url: str, api_key: str) -> dict:
    """Return a dict mapping project name -> project id for all active projects."""
    resp = requests.get(
        f"{base_url}/organization/projects",
        headers=_auth_headers(api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        p["name"]: p["id"]
        for p in data.get("data", [])
        if p.get("status") == "active"
    }


def create_project(base_url: str, api_key: str, name: str, tags: dict) -> dict:
    """Create a Bedrock Project and return the full response body."""
    resp = requests.post(
        f"{base_url}/organization/projects",
        headers=_auth_headers(api_key),
        json={"name": name, "tags": tags},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create project '{name}': {resp.status_code} — {resp.text}"
        )
    return resp.json()


def main():
    print("🧠 Creating Bedrock Projects for healthcare multi-tenant cost attribution...")

    region = get_aws_region() or os.environ.get("AWS_REGION", "us-east-1")
    base_url = _mantle_base_url(region)
    print(f"📍 Region: {region}")
    print(f"📍 Mantle endpoint: {base_url}")

    # Generate short-term Bedrock API key
    from aws_bedrock_token_generator import provide_token
    try:
        api_key = provide_token(region=region)
    except Exception as e:
        print(f"❌ Failed to generate Bedrock API token: {e}")
        print("   Ensure your AWS credentials have Bedrock permissions.")
        sys.exit(1)

    # Check for existing projects so we don't create duplicates
    existing = list_projects(base_url, api_key)

    for tier, cfg in TIER_PROJECTS.items():
        project_name = cfg["name"]
        ssm_param = cfg["ssm_param"]

        if project_name in existing:
            project_id = existing[project_name]
            print(f"⚠️  Project '{project_name}' already exists: {project_id}")
        else:
            print(f"\n📊 Creating {tier.capitalize()} Tier project...")
            project = create_project(base_url, api_key, project_name, cfg["tags"])
            project_id = project["id"]
            print(f"✅ Created project: {project_name}")
            print(f"   ID:   {project_id}")
            print(f"   ARN:  {project.get('arn', 'N/A')}")
            print(f"   Tags: {cfg['tags']}")

        # Store project ID in SSM
        put_ssm_parameter(ssm_param, project_id)
        print(f"✅ Stored {ssm_param} = {project_id} in SSM")

    print("\n✅ Bedrock Project creation completed!")
    print("   Basic:   Healthcare-Basic  (cost-effective tier)")
    print("   Premium: Healthcare-Premium (advanced reasoning tier)")
    print(
        "\n💡 Activate cost allocation tags in AWS Billing to see per-project costs "
        "in Cost Explorer. Tags may take up to 24 hours to propagate."
    )


if __name__ == "__main__":
    main()
