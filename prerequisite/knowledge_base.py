# Copyright 2024 Amazon.com and its affiliates; all rights reserved.
# This file is AWS Content and may not be duplicated or distributed without permission

"""
This module contains a helper class for building and using Knowledge Bases for Amazon Bedrock.
The KnowledgeBasesForAmazonBedrock class provides a convenient interface for working with Knowledge Bases.

It creates Bedrock Managed Knowledge Bases (type MANAGED), where Bedrock owns the
vector store, ingestion, indexing, and retrieval. Managed KBs are the type
required by the AgentCore Gateway managed KB connector target. The class also
handles the KB execution IAM role and S3 data source, and retains backward-
compatible cleanup for legacy VECTOR / S3 Vectors knowledge bases.
"""

import json
import sys
import boto3
import time
import uuid
from botocore.exceptions import ClientError
import pprint
from retrying import retry
import yaml
import os
import argparse

pp = pprint.PrettyPrinter(indent=2)


def read_yaml_file(file_path: str):
    """
    read and process a yaml file
    Args:
        file_path: the path to the yaml file
    """
    with open(file_path, "r", encoding="utf-8") as file:
        try:
            return yaml.safe_load(file)
        except yaml.YAMLError as e:
            print(f"Error reading YAML file: {e}")
            return None


def interactive_sleep(seconds: int):
    """
    Support functionality to induce an artificial 'sleep' to the code in order to wait for resources to be available
    Args:
        seconds (int): number of seconds to sleep for
    """
    dots = ""
    for i in range(seconds):
        dots += "."
        print(dots, end="\r")
        time.sleep(1)


class KnowledgeBasesForAmazonBedrock:
    """
    Support class that allows for:
        - creation (or retrieval) of a Knowledge Base for Amazon Bedrock with all its pre-requisites
          (including S3 Vectors, IAM roles and Permissions and S3 bucket)
        - Ingestion of data into the Knowledge Base
        - Deletion of all resources created
    """

    def __init__(self, suffix=None):
        """
        Class initializer
        """
        boto3_session = boto3.session.Session()
        self.region_name = boto3_session.region_name
        self.iam_client = boto3_session.client("iam", region_name=self.region_name)
        self.account_number = (
            boto3.client("sts", region_name=self.region_name)
            .get_caller_identity()
            .get("Account")
        )
        if suffix is not None:
            self.suffix = suffix
        else:
            self.suffix = str(uuid.uuid4())[:4]
        self.identity = boto3.client(
            "sts", region_name=self.region_name
        ).get_caller_identity()["Arn"]
        self.s3_vectors_client = boto3_session.client(
            "s3vectors", region_name=self.region_name
        )
        self.s3_client = boto3.client("s3", region_name=self.region_name)
        self.bedrock_agent_client = boto3.client(
            "bedrock-agent", region_name=self.region_name
        )
        self.vector_bucket_name = None
        self.index_name = None
        self.data_bucket_name = None

    def create_or_retrieve_knowledge_base(
        self,
        kb_name: str,
        kb_description: str = None,
        data_bucket_name: str = None,
    ):
        """
        Function used to create a new Knowledge Base or retrieve an existent one

        Args:
            kb_name: Knowledge Base Name
            kb_description: Knowledge Base Description
            data_bucket_name: Name of s3 Bucket containing Knowledge Base Data

        Returns:
            kb_id: str - Knowledge base id
            ds_id: str - Data Source id
        """
        kb_id = None
        ds_id = None
        kbs_available = self.bedrock_agent_client.list_knowledge_bases(
            maxResults=100,
        )
        for kb in kbs_available["knowledgeBaseSummaries"]:
            if kb_name == kb["name"]:
                kb_id = kb["knowledgeBaseId"]
        if kb_id is not None:
            ds_available = self.bedrock_agent_client.list_data_sources(
                knowledgeBaseId=kb_id,
                maxResults=100,
            )
            for ds in ds_available["dataSourceSummaries"]:
                if kb_id == ds["knowledgeBaseId"]:
                    ds_id = ds["dataSourceId"]
                    if not data_bucket_name:
                        self.data_bucket_name = self._get_knowledge_base_s3_bucket(
                            kb_id, ds_id
                        )
            print(f"Knowledge Base {kb_name} already exists.")
            print(f"Retrieved Knowledge Base Id: {kb_id}")
            print(f"Retrieved Data Source Id: {ds_id}")
        else:
            print(f"Creating KB {kb_name}")
            # self.kb_name = kb_name
            # self.kb_description = kb_description
            if data_bucket_name is None:
                kb_name_temp = kb_name.replace("_", "-")
                data_bucket_name = f"{kb_name_temp}-{self.suffix}"
                print(
                    f"KB bucket name not provided, creating a new one called: {data_bucket_name}"
                )
            kb_execution_role_name = (
                f"AmazonBedrockExecutionRoleForKnowledgeBase_{self.suffix}"
            )
            fm_policy_name = (
                f"AmazonBedrockFoundationModelPolicyForKnowledgeBase_{self.suffix}"
            )
            s3_policy_name = f"AmazonBedrockS3PolicyForKnowledgeBase_{self.suffix}"
            print(
                "========================================================================================"
            )
            print(
                f"Step 1 - Creating or retrieving {data_bucket_name} S3 bucket for Knowledge Base documents"
            )
            self.create_s3_bucket(data_bucket_name)
            print(
                "========================================================================================"
            )
            print(
                f"Step 2 - Creating Knowledge Base Execution Role ({kb_execution_role_name}) and Policies"
            )
            bedrock_kb_execution_role = self.create_bedrock_kb_execution_role(
                data_bucket_name,
                fm_policy_name,
                s3_policy_name,
                kb_execution_role_name,
            )
            print("Waiting for IAM policies to propagate...")
            time.sleep(10)
            print(
                "========================================================================================"
            )
            print("Step 3 - Creating Managed Knowledge Base")
            # A Bedrock Managed Knowledge Base provisions and manages its own
            # vector store, ingestion, and retrieval infrastructure — no S3
            # Vectors bucket/index or embedding-model plumbing required. This is
            # the KB type required by the AgentCore Gateway managed KB connector.
            knowledge_base, data_source = self.create_knowledge_base(
                data_bucket_name,
                kb_name,
                kb_description,
                bedrock_kb_execution_role,
            )
            interactive_sleep(60)
            print(
                "========================================================================================"
            )
            kb_id = knowledge_base["knowledgeBaseId"]
            ds_id = data_source["dataSourceId"]
        return kb_id, ds_id

    def create_s3_bucket(self, bucket_name: str):
        """
        Check if bucket exists, and if not create S3 bucket for knowledge base data source
        Args:
            bucket_name: s3 bucket name
        """
        self.data_bucket_name = bucket_name
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            print(f"Bucket {bucket_name} already exists - retrieving it!")
        except ClientError:
            print(f"Creating bucket {bucket_name}")
            if self.region_name == "us-east-1":
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": self.region_name},
                )
            # Enforce TLS-only access
            bucket_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "EnforceSecureTransport",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [
                            f"arn:aws:s3:::{bucket_name}",
                            f"arn:aws:s3:::{bucket_name}/*",
                        ],
                        "Condition": {
                            "Bool": {"aws:SecureTransport": "false"}
                        },
                    }
                ],
            }
            self.s3_client.put_bucket_policy(
                Bucket=bucket_name, Policy=json.dumps(bucket_policy)
            )

    def upload_directory(self, s3_path, bucket_name):
        """
        Upload files from a local path to s3 with metadata for clinic isolation.
        Preserves directory structure and adds metadata for Knowledge Base filtering.
        
        Args:
            s3_path: local path of the document directory
            bucket_name: bucket name
            
        Expected directory structure:
            s3_path/
                tier/              (e.g., basic-tier, premium-tier)
                    clinic-id/     (e.g., clinic-a, hospital-a)
                        doc-type/  (e.g., patient-intake, lab-results)
                            file.txt
        """
        base_path = os.path.abspath(s3_path)
        
        for root, dirs, files in os.walk(s3_path):
            for file in files:
                # Skip hidden files and system files
                if file.startswith('.'):
                    continue
                    
                file_to_upload = os.path.join(root, file)

                # Managed KBs require the typed metadata sidecar format. Upgrade
                # any legacy flat-format .metadata.json in place before upload so
                # clinic_id stays filterable regardless of when docs were generated.
                if file.endswith(".metadata.json"):
                    self._normalize_metadata_sidecar(file_to_upload)
                
                # Preserve directory structure as S3 key
                relative_path = os.path.relpath(file_to_upload, base_path)
                s3_key = relative_path.replace(os.sep, '/')  # Ensure forward slashes
                
                # Extract metadata from path structure
                # Expected: tier/clinic-id/doc-type/filename
                path_parts = relative_path.split(os.sep)
                metadata = {}
                
                if len(path_parts) >= 3:
                    metadata['tier'] = path_parts[0]
                    metadata['clinic_id'] = path_parts[1]
                    metadata['document_type'] = path_parts[2]
                elif len(path_parts) >= 2:
                    metadata['tier'] = path_parts[0]
                    metadata['clinic_id'] = path_parts[1]
                elif len(path_parts) >= 1:
                    # Fallback: try to extract from filename or path
                    metadata['tier'] = 'unknown'
                    metadata['clinic_id'] = 'unknown'
                
                print(f"Uploading: {file_to_upload}")
                print(f"  S3 Key: {s3_key}")
                print(f"  Metadata: {metadata}")
                
                # Upload with metadata
                self.s3_client.upload_file(
                    file_to_upload, 
                    bucket_name, 
                    s3_key,
                    ExtraArgs={'Metadata': metadata}
                )

    def _normalize_metadata_sidecar(self, metadata_file_path: str):
        """Ensure a .metadata.json sidecar uses the managed-KB typed format.

        Managed Knowledge Bases require each attribute to be shaped as
        {"value": {"type": "STRING"|"NUMBER"|"BOOLEAN", "<t>Value": ...}}.
        Older documents in this repo were written with a flat
        {"clinic_id": "hospital-a"} shape, which managed KBs will not index —
        silently breaking the clinic_id tenant filter. This upgrades any flat
        attributes in place and leaves already-typed attributes untouched.
        """
        try:
            with open(metadata_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ⚠️  Could not read metadata sidecar {metadata_file_path}: {e}")
            return

        attrs = data.get("metadataAttributes")
        if not isinstance(attrs, dict):
            return

        changed = False
        for key, val in list(attrs.items()):
            # Already typed (has a nested "value" dict) — leave as-is.
            if isinstance(val, dict) and "value" in val:
                continue
            if isinstance(val, bool):
                typed = {"type": "BOOLEAN", "booleanValue": val}
            elif isinstance(val, (int, float)):
                typed = {"type": "NUMBER", "numberValue": val}
            else:
                typed = {"type": "STRING", "stringValue": str(val)}
            attrs[key] = {"value": typed}
            changed = True

        if changed:
            with open(metadata_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  ✏️  Upgraded metadata sidecar to typed format: {metadata_file_path}")

    def get_data_bucket_name(self):
        """
        get the name of the data bucket
        """
        return self.data_bucket_name

    def _get_knowledge_base_s3_bucket(self, knowledge_base_id, data_source_id):
        """Get the s3 bucket associated with a knowledge base, if there is one"""
        try:
            # Get the data source details
            response = self.bedrock_agent_client.get_data_source(
                knowledgeBaseId=knowledge_base_id, dataSourceId=data_source_id
            )

            # Extract the S3 bucket information from the data source configuration
            data_source_config = response["dataSource"]["dataSourceConfiguration"]

            if data_source_config["type"] == "MANAGED_KNOWLEDGE_BASE_CONNECTOR":
                conn = data_source_config[
                    "managedKnowledgeBaseConnectorConfiguration"
                ]["connectorParameters"]
                # On read, connectorParameters comes back as a JSON string.
                if isinstance(conn, str):
                    conn = json.loads(conn)
                return conn.get("connectionConfiguration", {}).get("bucketName")
            elif data_source_config["type"] == "S3":
                # Legacy customer-managed vector KB data source.
                bucket_arn = data_source_config["s3Configuration"]["bucketArn"]
                return bucket_arn.split(":")[-1]
            else:
                return "Data source is not an S3 bucket"

        except Exception as e:
            print(f"Error retrieving data source information: {str(e)}")
            return None

    def create_bedrock_kb_execution_role(
        self,
        bucket_name: str,
        fm_policy_name: str,
        s3_policy_name: str,
        kb_execution_role_name: str,
    ):
        """
        Create Knowledge Base Execution IAM Role and its required policies.
        If role and/or policies already exist, retrieve them.

        For a Bedrock Managed Knowledge Base, the service uses a service-managed
        embedding model, so the role only needs permission to discover models
        (ListFoundationModels/ListCustomModels) plus S3 read access to the data
        source. See the managed KB service role docs.

        Args:
            bucket_name: the bucket name used by the knowledge base
            fm_policy_name: the name of the foundation model access policy
            s3_policy_name: the name of the s3 access policy
            kb_execution_role_name: the name of the knowledge base execution role

        Returns:
            IAM role created
        """
        foundation_model_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "bedrock:ListFoundationModels",
                        "bedrock:ListCustomModels",
                    ],
                    "Resource": "*",
                }
            ],
        }

        s3_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:ListBucket"],
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}",
                        f"arn:aws:s3:::{bucket_name}/*",
                    ],
                    "Condition": {
                        "StringEquals": {
                            "aws:ResourceAccount": f"{self.account_number}"
                        }
                    },
                }
            ],
        }

        assume_role_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {"aws:SourceAccount": f"{self.account_number}"},
                        "ArnLike": {
                            "aws:SourceArn": f"arn:aws:bedrock:{self.region_name}:{self.account_number}:knowledge-base/*"
                        },
                    },
                }
            ],
        }

        try:
            # create policies based on the policy documents
            fm_policy = self.iam_client.create_policy(
                PolicyName=fm_policy_name,
                PolicyDocument=json.dumps(foundation_model_policy_document),
                Description="Policy for accessing foundation model",
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print(f"{fm_policy_name} already exists, retrieving it!")
            fm_policy = self.iam_client.get_policy(
                PolicyArn=f"arn:aws:iam::{self.account_number}:policy/{fm_policy_name}"
            )

        try:
            s3_policy = self.iam_client.create_policy(
                PolicyName=s3_policy_name,
                PolicyDocument=json.dumps(s3_policy_document),
                Description="Policy for reading documents from s3",
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print(f"{s3_policy_name} already exists, retrieving it!")
            s3_policy = self.iam_client.get_policy(
                PolicyArn=f"arn:aws:iam::{self.account_number}:policy/{s3_policy_name}"
            )
        # create bedrock execution role
        try:
            bedrock_kb_execution_role = self.iam_client.create_role(
                RoleName=kb_execution_role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy_document),
                Description="Amazon Bedrock Knowledge Base Execution Role for accessing OSS and S3",
                MaxSessionDuration=3600,
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print(f"{kb_execution_role_name} already exists, retrieving it!")
            bedrock_kb_execution_role = self.iam_client.get_role(
                RoleName=kb_execution_role_name
            )
        # fetch arn of the policies and role created above
        s3_policy_arn = s3_policy["Policy"]["Arn"]
        fm_policy_arn = fm_policy["Policy"]["Arn"]

        # attach policies to Amazon Bedrock execution role
        self.iam_client.attach_role_policy(
            RoleName=bedrock_kb_execution_role["Role"]["RoleName"],
            PolicyArn=fm_policy_arn,
        )
        self.iam_client.attach_role_policy(
            RoleName=bedrock_kb_execution_role["Role"]["RoleName"],
            PolicyArn=s3_policy_arn,
        )
        return bedrock_kb_execution_role

    @retry(wait_random_min=1000, wait_random_max=2000, stop_max_attempt_number=7)
    def create_knowledge_base(
        self,
        bucket_name: str,
        kb_name: str,
        kb_description: str,
        bedrock_kb_execution_role: str,
    ):
        """
        Create a Bedrock Managed Knowledge Base and its S3 Data Source. If
        existent, retrieve.

        A managed KB (type MANAGED) has Bedrock manage the vector store,
        ingestion, indexing, and retrieval — so there is no storageConfiguration
        and no embedding-model ARN to supply (a service-managed embedding model
        is used by default). This is the KB type required by the AgentCore
        Gateway managed KB connector.

        Args:
            bucket_name: name of the s3 bucket containing the knowledge base data
            kb_name: knowledge base name
            kb_description: knowledge base description
            bedrock_kb_execution_role: knowledge base execution role

        Returns:
            knowledge base object,
            data source object
        """
        # Note: a managed KB with the default managed embedding model does its
        # own chunking — passing a chunkingConfiguration is rejected, so we omit
        # vectorIngestionConfiguration entirely below.

        # Managed KBs require the MANAGED_KNOWLEDGE_BASE_CONNECTOR data source
        # type with an S3 connectorParameters block (not the plain S3 data
        # source used by customer-managed vector KBs). Metadata sidecar files
        # (.metadata.json) alongside each document carry the filterable
        # clinic_id attribute used for tenant isolation.
        managed_connector_configuration = {
            "connectorParameters": {
                "type": "S3",
                "version": "1",
                "connectionConfiguration": {
                    "bucketName": bucket_name,
                    "bucketOwnerAccountId": self.account_number,
                },
            }
        }

        kb = None
        try:
            print(bedrock_kb_execution_role["Role"]["Arn"])
            create_kb_response = self.bedrock_agent_client.create_knowledge_base(
                name=kb_name,
                description=kb_description,
                roleArn=bedrock_kb_execution_role["Role"]["Arn"],
                knowledgeBaseConfiguration={
                    "type": "MANAGED",
                    "managedKnowledgeBaseConfiguration": {
                        # Service-managed embedding model (no ARN required).
                        "embeddingModelType": "MANAGED",
                    },
                },
            )
            kb = create_kb_response["knowledgeBase"]
            pp.pprint(kb)
        except self.bedrock_agent_client.exceptions.ConflictException:
            kbs = self.bedrock_agent_client.list_knowledge_bases(maxResults=100)
            kb_id = None
            for existing in kbs["knowledgeBaseSummaries"]:
                if existing["name"] == kb_name:
                    kb_id = existing["knowledgeBaseId"]
            kb = self.bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)[
                "knowledgeBase"
            ]
            pp.pprint(kb)

        # A managed KB must reach ACTIVE before a data source can be created —
        # otherwise CreateDataSource fails with "not in a valid status".
        self._wait_for_kb_active(kb["knowledgeBaseId"])

        # If a data source already exists (e.g. re-run after a partial failure),
        # reuse it instead of creating a duplicate.
        existing_ds = self.bedrock_agent_client.list_data_sources(
            knowledgeBaseId=kb["knowledgeBaseId"], maxResults=100
        ).get("dataSourceSummaries", [])
        if existing_ds:
            ds_id = existing_ds[0]["dataSourceId"]
            ds = self.bedrock_agent_client.get_data_source(
                dataSourceId=ds_id, knowledgeBaseId=kb["knowledgeBaseId"]
            )["dataSource"]
            print(f"Data source already exists for {kb_name}, reusing it.")
            pp.pprint(ds)
            return kb, ds

        # Create a DataSource in KnowledgeBase
        create_ds_response = self.bedrock_agent_client.create_data_source(
            name=kb_name,
            description=kb_description,
            knowledgeBaseId=kb["knowledgeBaseId"],
            dataDeletionPolicy="RETAIN",
            dataSourceConfiguration={
                "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                "managedKnowledgeBaseConnectorConfiguration": managed_connector_configuration,
            },
        )
        ds = create_ds_response["dataSource"]
        pp.pprint(ds)
        return kb, ds

    def _wait_for_kb_active(self, kb_id: str, max_wait_seconds: int = 300) -> None:
        """Block until the knowledge base leaves a transitional status.

        Managed KBs take longer to provision than legacy vector KBs, so we poll
        get_knowledge_base until it is no longer CREATING/UPDATING before
        attaching a data source.
        """
        transitional = ("CREATING", "UPDATING")
        start = time.time()
        while time.time() - start < max_wait_seconds:
            status = self.bedrock_agent_client.get_knowledge_base(
                knowledgeBaseId=kb_id
            )["knowledgeBase"]["status"]
            if status not in transitional:
                print(f"Knowledge base {kb_id} status: {status}")
                return
            print(f"Waiting for knowledge base {kb_id} to become ACTIVE (status: {status})...")
            time.sleep(10)
        print(f"⚠️  Timed out waiting for knowledge base {kb_id} to become ACTIVE")

    def synchronize_data(self, kb_id, ds_id):
        """
        Start an ingestion job to synchronize data from an S3 bucket to the Knowledge Base
        and waits for the job to be completed
        Args:
            kb_id: knowledge base id
            ds_id: data source id
        """
        # ensure that the kb is available
        i_status = ["CREATING", "DELETING", "UPDATING"]
        while (
            self.bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)[
                "knowledgeBase"
            ]["status"]
            in i_status
        ):
            time.sleep(10)
        # Start an ingestion job
        start_job_response = self.bedrock_agent_client.start_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id
        )
        job = start_job_response["ingestionJob"]
        pp.pprint(job)
        # Get job
        while job["status"] != "COMPLETE" and job["status"] != "FAILED":
            get_job_response = self.bedrock_agent_client.get_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                ingestionJobId=job["ingestionJobId"],
            )
            job = get_job_response["ingestionJob"]
            interactive_sleep(5)
        pp.pprint(job)
        # interactive_sleep(40)

    def get_kb(self, kb_id):
        """
        Get KB details
        Args:
            kb_id: knowledge base id
        """
        get_job_response = self.bedrock_agent_client.get_knowledge_base(
            knowledgeBaseId=kb_id
        )
        return get_job_response

    def delete_kb(
        self,
        kb_name: str,
        delete_s3_bucket: bool = True,
        delete_iam_roles_and_policies: bool = True,
        delete_s3_vector: bool = True,
    ):
        """
        Delete the Knowledge Base resources
        Args:
            kb_name: name of the knowledge base to delete
            delete_s3_bucket (bool): boolean to indicate if s3 bucket should also be deleted
            delete_iam_roles_and_policies (bool): boolean to indicate if IAM roles and Policies should also be deleted
            delete_s3_vector: boolean to indicate if amazon Amazon S3 Vector
        """
        kbs_available = self.bedrock_agent_client.list_knowledge_bases(
            maxResults=100,
        )
        kb_id = None
        ds_id = None
        for kb in kbs_available["knowledgeBaseSummaries"]:
            if kb_name == kb["name"]:
                kb_id = kb["knowledgeBaseId"]

        if kb_id is None:
            print(f"Knowledge base '{kb_name}' not found — nothing to delete.")
            return

        # Deleting a KB that is still CREATING/UPDATING fails; wait it out.
        self._wait_for_kb_active(kb_id)

        kb_details = self.bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)
        kb_role = kb_details["knowledgeBase"]["roleArn"].split("/")[1]

        # Managed KBs own their datastore, so there is no S3 Vectors bucket/index
        # to delete. Detect any legacy VECTOR/S3_VECTORS KB for backward compat.
        storage_config = kb_details["knowledgeBase"].get("storageConfiguration", {})
        s3_vectors_config = storage_config.get("s3VectorsConfiguration")
        vector_bucket_arn = s3_vectors_config.get("vectorBucketArn") if s3_vectors_config else None
        index_arn = s3_vectors_config.get("indexArn") if s3_vectors_config else None

        # A partially-created KB may have no data source yet.
        ds_available = self.bedrock_agent_client.list_data_sources(
            knowledgeBaseId=kb_id,
            maxResults=100,
        )
        for ds in ds_available["dataSourceSummaries"]:
            if kb_id == ds["knowledgeBaseId"]:
                ds_id = ds["dataSourceId"]

        # Only legacy VECTOR/S3_VECTORS knowledge bases have an S3 Vectors
        # bucket/index to remove. Managed KBs manage their own datastore.
        if delete_s3_vector and index_arn and vector_bucket_arn:
            self.s3_vectors_client.delete_index(
                indexArn=index_arn,
            )
            print("S3 Vectors index deleted successfully!")

            self.s3_vectors_client.delete_vector_bucket(
                vectorBucketArn=vector_bucket_arn,
            )
            print("S3 Vectors bucket deleted successfully!")
        elif delete_s3_vector:
            print("Managed KB (no S3 Vectors resources to delete), skipping.")

        # Delete the data source first (if one exists), then the KB.
        if ds_id is not None:
            self.bedrock_agent_client.delete_data_source(
                dataSourceId=ds_id, knowledgeBaseId=kb_id
            )
            print("Data Source deleted successfully!")
        else:
            print("No data source found for this knowledge base, skipping.")

        self.bedrock_agent_client.delete_knowledge_base(knowledgeBaseId=kb_id)
        print("Knowledge Base deleted successfully!")

        if delete_iam_roles_and_policies:
            self.delete_iam_roles_and_policies(kb_role)
            print("Knowledge Base Roles and Policies deleted successfully!")

        print("Resources deleted successfully!")

    def delete_iam_roles_and_policies(self, kb_execution_role_name: str):
        """
        Delete IAM Roles and policies used by the Knowledge Base
        Args:
            kb_execution_role_name: knowledge base execution role
        """
        attached_policies = self.iam_client.list_attached_role_policies(
            RoleName=kb_execution_role_name, MaxItems=100
        )
        policies_arns = []
        for policy in attached_policies["AttachedPolicies"]:
            policies_arns.append(policy["PolicyArn"])
        for policy in policies_arns:
            self.iam_client.detach_role_policy(
                RoleName=kb_execution_role_name, PolicyArn=policy
            )
            self.iam_client.delete_policy(PolicyArn=policy)
        self.iam_client.delete_role(RoleName=kb_execution_role_name)
        return 0

    def delete_s3(self, bucket_name: str):
        """
        Delete the objects contained in the Knowledge Base S3 bucket.
        Once the bucket is empty, delete the bucket
        Args:
            bucket_name: bucket name

        """
        objects = self.s3_client.list_objects(Bucket=bucket_name)
        if "Contents" in objects:
            for obj in objects["Contents"]:
                self.s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
        self.s3_client.delete_bucket(Bucket=bucket_name)


if __name__ == "__main__":
    kb = KnowledgeBasesForAmazonBedrock()
    smm_client = boto3.client("ssm")
    current_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="Knowledge Base handler")
    parser.add_argument(
        "--mode",
        required=True,
        help="Knowledge Base helper mode. One of: create or delete.",
    )
    parser.add_argument(
        "--config",
        default="prereqs_config.yaml",
        help="Config file name (default: prereqs_config.yaml). Use premium_prereqs_config.yaml for premium tier.",
    )

    args = parser.parse_args()

    # Load config file
    config_path = f"{current_dir}/{args.config}"
    data = read_yaml_file(config_path)
    
    if not data:
        print(f"❌ Failed to read config file: {config_path}")
        sys.exit(1)

    print(data)
    if args.mode == "create":
        kb_id, ds_id = kb.create_or_retrieve_knowledge_base(
            data["knowledge_base_name"], data["knowledge_base_description"]
        )
        print(f"Knowledge Base ID: {kb_id}")
        print(f"Data Source ID: {ds_id}")

        kb.upload_directory(
            f"{current_dir}/{data['kb_files_path']}", kb.get_data_bucket_name()
        )
        kb.synchronize_data(kb_id, ds_id)

        # Determine tier from KB name (basic or premium)
        tier = "basic" if "basic" in data["knowledge_base_name"].lower() else "premium"
        
        smm_client.put_parameter(
            Name=f"/app/healthcare/knowledge_base/{tier}_kb_id",
            Description=f"{data['knowledge_base_name']} kb id",
            Value=kb_id,
            Type="String",
            Overwrite=True,
        )
        
        smm_client.put_parameter(
            Name=f"/app/healthcare/knowledge_base/{tier}_ds_id",
            Description=f"{data['knowledge_base_name']} data source id",
            Value=ds_id,
            Type="String",
            Overwrite=True,
        )

    if args.mode == "delete":
        kb.delete_kb(data["knowledge_base_name"])
        
        # Determine tier from KB name (basic or premium)
        tier = "basic" if "basic" in data["knowledge_base_name"].lower() else "premium"
        
        try:
            smm_client.delete_parameter(
                Name=f"/app/healthcare/knowledge_base/{tier}_kb_id"
            )
        except smm_client.exceptions.ParameterNotFound:
            print(f"Parameter /app/healthcare/knowledge_base/{tier}_kb_id not found")
        
        try:
            smm_client.delete_parameter(
                Name=f"/app/healthcare/knowledge_base/{tier}_ds_id"
            )
        except smm_client.exceptions.ParameterNotFound:
            print(f"Parameter /app/healthcare/knowledge_base/{tier}_ds_id not found")
