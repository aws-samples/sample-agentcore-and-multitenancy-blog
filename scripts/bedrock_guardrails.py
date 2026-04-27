#!/usr/bin/env python3
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Bedrock Guardrails Management for Healthcare Multi-Tenancy

Creates tier-specific guardrails:
  - Basic:   content filters, denied topics, PII filtering, prompt attack detection
  - Premium: all basic protections + contextual grounding, sensitive info regex filters

Usage:
    python scripts/bedrock_guardrails.py create     # Create both guardrails
    python scripts/bedrock_guardrails.py delete      # Delete both guardrails
    python scripts/bedrock_guardrails.py status      # Show guardrail status
"""

import sys
import boto3
import click

from utils import (
    get_aws_region,
    get_ssm_parameter,
    put_ssm_parameter,
    delete_ssm_parameter,
)

REGION = get_aws_region()
bedrock_client = boto3.client("bedrock", region_name=REGION)


# ---------------------------------------------------------------------------
# Shared policy configs (both tiers)
# ---------------------------------------------------------------------------

BLOCKED_INPUT_MESSAGE = (
    "Your request was blocked by our safety policy. "
    "Please rephrase your question to focus on clinical document retrieval."
)

BLOCKED_OUTPUT_MESSAGE = (
    "The response was blocked by our safety policy. "
    "Please try a different question."
)

# Content filters — block harmful content at high thresholds
CONTENT_FILTERS = [
    {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
    {"type": "INSULTS", "inputStrength": "HIGH", "outputStrength": "HIGH"},
    {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
    {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
    {"type": "MISCONDUCT", "inputStrength": "HIGH", "outputStrength": "HIGH"},
    {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
]

# Denied topics — the agent retrieves records, it should not practice medicine
DENIED_TOPICS = [
    {
        "name": "medical-diagnosis",
        "definition": (
            "Providing specific medical diagnoses, interpreting test results to "
            "conclude a disease or condition, or telling a patient what condition "
            "they have based on symptoms or lab values."
        ),
        "examples": [
            "Based on your lab results, you have diabetes.",
            "These symptoms indicate you have pneumonia.",
            "Your cholesterol levels mean you have heart disease.",
        ],
        "type": "DENY",
    },
    {
        "name": "treatment-prescription",
        "definition": (
            "Recommending specific treatments, prescribing medications, suggesting "
            "dosages, or advising on whether to start, stop, or change medications."
        ),
        "examples": [
            "You should take 500mg of metformin twice daily.",
            "I recommend starting chemotherapy immediately.",
            "Stop taking your blood pressure medication.",
        ],
        "type": "DENY",
    },
    {
        "name": "legal-advice",
        "definition": (
            "Providing legal opinions, malpractice assessments, or advice on "
            "healthcare regulations and compliance matters."
        ),
        "examples": [
            "You have grounds for a malpractice lawsuit.",
            "This treatment violates HIPAA regulations.",
            "The clinic is liable for this outcome.",
        ],
        "type": "DENY",
    },
]

# PII entities to filter (shared baseline)
SHARED_PII_ENTITIES = [
    {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "ANONYMIZE"},
    {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "ANONYMIZE"},
    {"type": "CREDIT_DEBIT_CARD_CVV", "action": "ANONYMIZE"},
    {"type": "CREDIT_DEBIT_CARD_EXPIRY", "action": "ANONYMIZE"},
    {"type": "INTERNATIONAL_BANK_ACCOUNT_NUMBER", "action": "ANONYMIZE"},
    {"type": "DRIVER_ID", "action": "ANONYMIZE"},
    {"type": "US_PASSPORT_NUMBER", "action": "ANONYMIZE"},
    {"type": "PIN", "action": "ANONYMIZE"},
    {"type": "IP_ADDRESS", "action": "ANONYMIZE"},
]

# Word filter — profanity
MANAGED_WORD_LISTS = [{"type": "PROFANITY"}]


# ---------------------------------------------------------------------------
# Premium-only policy configs
# ---------------------------------------------------------------------------

# Contextual grounding — catch hallucinations in multi-source synthesis
CONTEXTUAL_GROUNDING_FILTERS = [
    {"type": "GROUNDING", "threshold": 0.8, "action": "BLOCK"},
    {"type": "RELEVANCE", "threshold": 0.7, "action": "BLOCK"},
]

# Additional PII entities for premium (more sensitive clinical data)
PREMIUM_EXTRA_PII = [
    {"type": "EMAIL", "action": "ANONYMIZE"},
    {"type": "PHONE", "action": "ANONYMIZE"},
    {"type": "NAME", "action": "ANONYMIZE"},
    {"type": "ADDRESS", "action": "ANONYMIZE"},
]

# Regex filters for premium — mask medical record numbers and DEA numbers
PREMIUM_REGEX_FILTERS = [
    {
        "name": "medical-record-number",
        "description": "Medical Record Number (MRN) patterns",
        "pattern": r"\bMRN[-:\s]?\d{6,10}\b",
        "action": "ANONYMIZE",
    },
    {
        "name": "dea-number",
        "description": "DEA registration number pattern",
        "pattern": r"\b[A-Z]{2}\d{7}\b",
        "action": "ANONYMIZE",
    },
    {
        "name": "npi-number",
        "description": "National Provider Identifier (NPI) pattern",
        "pattern": r"\bNPI[-:\s]?\d{10}\b",
        "action": "ANONYMIZE",
    },
]


def _build_guardrail_config(tier: str) -> dict:
    """Build the CreateGuardrail request body for a given tier."""
    config = {
        "name": f"healthcare-{tier}-guardrail",
        "description": f"Healthcare {tier.title()} tier guardrail — content safety, denied topics, PII filtering"
        + (", contextual grounding" if tier == "premium" else ""),
        "blockedInputMessaging": BLOCKED_INPUT_MESSAGE,
        "blockedOutputsMessaging": BLOCKED_OUTPUT_MESSAGE,
        "contentPolicyConfig": {
            "filtersConfig": CONTENT_FILTERS,
        },
        "topicPolicyConfig": {
            "topicsConfig": DENIED_TOPICS,
        },
        "wordPolicyConfig": {
            "managedWordListsConfig": MANAGED_WORD_LISTS,
        },
        "sensitiveInformationPolicyConfig": {
            "piiEntitiesConfig": list(SHARED_PII_ENTITIES),
        },
        "tags": [
            {"key": "Application", "value": "Healthcare"},
            {"key": "Tier", "value": tier},
        ],
    }

    if tier == "premium":
        # Add contextual grounding
        config["contextualGroundingPolicyConfig"] = {
            "filtersConfig": CONTEXTUAL_GROUNDING_FILTERS,
        }
        config["description"] = (
            "Healthcare Premium tier guardrail — content safety, denied topics, "
            "PII filtering, contextual grounding, sensitive info regex"
        )
        # Add extra PII entities
        config["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"].extend(
            PREMIUM_EXTRA_PII
        )
        # Add regex filters
        config["sensitiveInformationPolicyConfig"]["regexesConfig"] = (
            PREMIUM_REGEX_FILTERS
        )

    return config


def create_guardrail(tier: str) -> dict:
    """Create a Bedrock Guardrail for the specified tier."""
    config = _build_guardrail_config(tier)
    guardrail_name = config["name"]

    click.echo(f"\n{'='*60}")
    click.echo(f"Creating {tier.title()} Tier Guardrail: {guardrail_name}")
    click.echo(f"{'='*60}")

    try:
        resp = bedrock_client.create_guardrail(**config)
        guardrail_id = resp["guardrailId"]
        guardrail_arn = resp["guardrailArn"]
        version = resp["version"]

        click.echo(f"✅ Guardrail created: {guardrail_id} (version {version})")

        # Save to SSM
        put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_id", guardrail_id)
        put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_arn", guardrail_arn)
        put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_version", version)

        click.echo(f"✅ SSM parameters saved for {tier} tier")

        return {
            "id": guardrail_id,
            "arn": guardrail_arn,
            "version": version,
            "tier": tier,
        }

    except bedrock_client.exceptions.ConflictException:
        click.echo(f"⚠️  Guardrail '{guardrail_name}' already exists, looking up...")
        return _find_existing_guardrail(tier, guardrail_name)

    except Exception as e:
        click.echo(f"❌ Failed to create guardrail: {e}", err=True)
        sys.exit(1)


def _find_existing_guardrail(tier: str, guardrail_name: str) -> dict:
    """Find an existing guardrail by name and update SSM parameters."""
    paginator = bedrock_client.get_paginator("list_guardrails")
    for page in paginator.paginate():
        for gd in page.get("guardrails", []):
            if gd["name"] == guardrail_name:
                guardrail_id = gd["id"]
                # Get full details
                detail = bedrock_client.get_guardrail(guardrailIdentifier=guardrail_id)
                version = detail.get("version", "DRAFT")
                guardrail_arn = detail.get("guardrailArn", "")

                put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_id", guardrail_id)
                put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_arn", guardrail_arn)
                put_ssm_parameter(f"/app/healthcare/guardrails/{tier}_version", version)

                click.echo(f"✅ Found existing guardrail: {guardrail_id} (version {version})")
                return {
                    "id": guardrail_id,
                    "arn": guardrail_arn,
                    "version": version,
                    "tier": tier,
                }

    click.echo(f"❌ Could not find existing guardrail '{guardrail_name}'", err=True)
    sys.exit(1)


def delete_guardrail(tier: str) -> bool:
    """Delete a guardrail for the specified tier."""
    try:
        guardrail_id = get_ssm_parameter(f"/app/healthcare/guardrails/{tier}_id")
    except Exception:
        click.echo(f"⚠️  No {tier} guardrail found in SSM")
        return False

    try:
        bedrock_client.delete_guardrail(guardrailIdentifier=guardrail_id)
        click.echo(f"✅ Deleted {tier} guardrail: {guardrail_id}")
    except Exception as e:
        click.echo(f"❌ Error deleting {tier} guardrail: {e}", err=True)
        return False

    # Clean up SSM
    delete_ssm_parameter(f"/app/healthcare/guardrails/{tier}_id")
    delete_ssm_parameter(f"/app/healthcare/guardrails/{tier}_arn")
    delete_ssm_parameter(f"/app/healthcare/guardrails/{tier}_version")
    click.echo(f"🧹 Cleaned up {tier} guardrail SSM parameters")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Bedrock Guardrails Management for Healthcare Multi-Tenancy."""
    pass


@cli.command()
def create():
    """Create both basic and premium tier guardrails."""
    click.echo("🛡️  Creating Bedrock Guardrails for Healthcare")
    click.echo(f"📍 Region: {REGION}")

    results = {}
    for tier in ("basic", "premium"):
        results[tier] = create_guardrail(tier)

    click.echo(f"\n{'='*60}")
    click.echo("🎉 Guardrails created successfully!")
    click.echo(f"{'='*60}")
    click.echo(f"Basic:   {results['basic']['id']} (v{results['basic']['version']})")
    click.echo(f"Premium: {results['premium']['id']} (v{results['premium']['version']})")
    click.echo()
    click.echo("Shared policies (both tiers):")
    click.echo("  - Content filters (hate, insults, sexual, violence, misconduct, prompt attack)")
    click.echo("  - Denied topics (medical diagnosis, treatment prescription, legal advice)")
    click.echo("  - PII anonymization (SSN, credit cards, driver ID, passport)")
    click.echo("  - Profanity word filter")
    click.echo()
    click.echo("Premium-only policies:")
    click.echo("  - Contextual grounding (threshold: 0.8 grounding, 0.7 relevance)")
    click.echo("  - Additional PII (email, phone, name, address)")
    click.echo("  - Regex filters (MRN, DEA number, NPI number)")


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(confirm):
    """Delete both basic and premium tier guardrails."""
    if not confirm:
        if not click.confirm("⚠️  Delete both guardrails?"):
            click.echo("Cancelled")
            sys.exit(0)

    for tier in ("basic", "premium"):
        delete_guardrail(tier)

    click.echo("🎉 All guardrails deleted")


@cli.command()
def status():
    """Show current guardrail status."""
    click.echo("📋 Bedrock Guardrails Status")
    click.echo("=" * 60)

    for tier in ("basic", "premium"):
        try:
            guardrail_id = get_ssm_parameter(f"/app/healthcare/guardrails/{tier}_id")
            detail = bedrock_client.get_guardrail(guardrailIdentifier=guardrail_id)
            click.echo(f"\n{tier.capitalize()} Tier:")
            click.echo(f"  ID:      {guardrail_id}")
            click.echo(f"  Name:    {detail.get('name')}")
            click.echo(f"  Status:  {detail.get('status')}")
            click.echo(f"  Version: {detail.get('version')}")
        except Exception as e:
            click.echo(f"\n{tier.capitalize()} Tier: Not configured ({e})")


if __name__ == "__main__":
    cli()
