# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
ABAC-scoped credential factory for AgentCore Memory.

Creates per-tenant STS sessions with tags that IAM evaluates against
the TVM role's ABAC policy. This moves memory isolation from
application-level enforcement to IAM-level enforcement.

The actor_id format stays as: {tier}-{clinic_id}-{user_id}
Namespaces stay as: clinic/{actor_id}/facts/... and clinic/{actor_id}/preferences

Flow:
  1. Agent execution role assumes the TVM (Token Vending Machine) role
  2. STS session is tagged with Tier, ClinicId, UserId
  3. Tags are marked transitive so they propagate through chained calls
  4. The TVM role's policy uses condition keys:
     - bedrock-agentcore:actorId  (must match {Tier}-{ClinicId}-{UserId})
     - bedrock-agentcore:namespace (must match /clinic/{Tier}-{ClinicId}-{UserId}/*)
  5. MemoryClient is created with the scoped credentials
"""

import os
import re
import logging

import boto3
from bedrock_agentcore.memory import MemoryClient

from .utils import get_ssm_parameter

logger = logging.getLogger(__name__)

# SSM parameter for the TVM role ARN
TVM_ROLE_SSM = "/app/healthcare/memory/tvm_role_arn"

SESSION_DURATION = 900

_SESSION_NAME_RE = re.compile(r"[^\w+=,.@-]")


def _sanitize_session_name(raw: str, max_len: int = 64) -> str:
    return _SESSION_NAME_RE.sub("_", raw)[:max_len]


def _get_tvm_role_arn() -> str:
    """Resolve the TVM role ARN from SSM (cached by get_ssm_parameter)."""
    return get_ssm_parameter(TVM_ROLE_SSM)


def assume_scoped_role(tier: str, clinic_id: str, user_id: str) -> dict:
    """
    Assume the TVM role with session tags for ABAC-scoped memory access.

    Returns the temporary credentials dict from STS with keys:
      AccessKeyId, SecretAccessKey, SessionToken, Expiration
    """
    tvm_role_arn = _get_tvm_role_arn()
    session_name = _sanitize_session_name(f"mem-{tier}-{clinic_id}-{user_id}")

    sts = boto3.client("sts", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    logger.info(
        f"Assuming TVM role for memory ABAC: role={tvm_role_arn}, "
        f"tier={tier}, clinic={clinic_id}, user={user_id}"
    )

    response = sts.assume_role(
        RoleArn=tvm_role_arn,
        RoleSessionName=session_name,
        DurationSeconds=SESSION_DURATION,
        Tags=[
            {"Key": "Tier", "Value": tier},
            {"Key": "ClinicId", "Value": clinic_id},
            {"Key": "UserId", "Value": user_id},
        ],
        TransitiveTagKeys=["Tier", "ClinicId", "UserId"],
    )

    return response["Credentials"]


def create_scoped_memory_client(
    tier: str, clinic_id: str, user_id: str
) -> MemoryClient:
    """
    Create a MemoryClient backed by ABAC-scoped temporary credentials.

    MemoryClient doesn't accept a boto session, so we construct it normally
    then replace its internal boto3 clients with ones using scoped credentials.
    """
    creds = assume_scoped_role(tier, clinic_id, user_id)
    region = os.environ.get("AWS_REGION", "us-east-1")

    scoped_session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )

    # Build the client normally, then swap in scoped boto3 clients
    memory_client = MemoryClient(region_name=region)
    memory_client.gmcp_client = scoped_session.client("bedrock-agentcore-control", region_name=region)
    memory_client.gmdp_client = scoped_session.client("bedrock-agentcore", region_name=region)

    actor_id = f"{tier}-{clinic_id}-{user_id}"
    logger.info(f"Created ABAC-scoped MemoryClient for actor_id={actor_id}")

    return memory_client
