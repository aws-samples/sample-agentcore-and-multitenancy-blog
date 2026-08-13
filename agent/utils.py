# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os

# Shared SSM paths — keep in sync with scripts/utils.py
REGISTRY_ID_SSM_PATH = "/app/healthcare/agentcore/registry_id"


def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    ssm = boto3.client("ssm", region_name=region)
    response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)
    return response["Parameter"]["Value"]
