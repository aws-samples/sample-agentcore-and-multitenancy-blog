#!/usr/bin/env python3

"""
Script to create premium tenant knowledge base
"""

import os
import sys
import boto3
from knowledge_base import KnowledgeBasesForAmazonBedrock, read_yaml_file

def main():
    """Create premium tenant knowledge base"""
    
    # Initialize clients
    kb = KnowledgeBasesForAmazonBedrock()
    ssm_client = boto3.client("ssm")
    
    # Get current directory and config
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = f"{current_dir}/premium_prereqs_config.yaml"
    
    # Read premium config
    data = read_yaml_file(config_path)
    if not data:
        print("❌ Failed to read premium config file")
        sys.exit(1)
    
    print(f"Creating premium knowledge base: {data['knowledge_base_name']}")
    
    try:
        # Create premium knowledge base
        kb_id, ds_id = kb.create_or_retrieve_knowledge_base(
            data["knowledge_base_name"], 
            data["knowledge_base_description"]
        )
        
        print(f"✅ Premium Knowledge Base ID: {kb_id}")
        print(f"✅ Premium Data Source ID: {ds_id}")
        
        # Update SSM parameters for healthcare
        ssm_client.put_parameter(
            Name="/app/healthcare/knowledge_base/premium_kb_id",
            Description=f"{data['knowledge_base_name']} kb id",
            Value=kb_id,
            Type="String",
            Overwrite=True
        )
        
        ssm_client.put_parameter(
            Name="/app/healthcare/knowledge_base/premium_ds_id",
            Description=f"{data['knowledge_base_name']} data source id",
            Value=ds_id,
            Type="String",
            Overwrite=True
        )
        
        print("✅ Updated SSM parameters")
        
        # Upload premium policies to S3
        kb.upload_directory(data["kb_files_path"], kb.get_data_bucket_name())
        print("✅ Uploaded premium policies to S3")
        
        # Sync data source
        kb.synchronize_data(kb_id, ds_id)
        print("✅ Started ingestion job for premium knowledge base")
        
    except Exception as e:
        print(f"❌ Error creating premium knowledge base: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
