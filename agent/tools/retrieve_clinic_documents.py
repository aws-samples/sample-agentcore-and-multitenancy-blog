"""Knowledge Base retrieval with clinic-level metadata filtering for tenant isolation."""

import boto3
import os
from strands import tool


@tool
def retrieve_clinic_documents(query: str, clinic_id: str, max_results: int = 5) -> str:
    """
    Search the knowledge base for clinical documents, filtered to the requesting clinic.

    Tenant isolation is enforced via a metadata filter on clinic_id — each clinic
    can only retrieve documents tagged with their own identifier.

    Args:
        query: Question about clinical documents, patient information, or medical procedures.
        clinic_id: Clinic identifier for metadata filtering.
        max_results: Number of results to return (default: 5).

    Returns:
        Formatted string with matching document content.
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID")

    if not kb_id:
        return "Error: Knowledge Base ID not configured."

    client = boto3.client("bedrock-agent-runtime", region_name=region)

    try:
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": max_results,
                    "filter": {"equals": {"key": "clinic_id", "value": clinic_id}},
                }
            },
        )

        results = [
            r.get("content", {}).get("text", "")
            for r in response.get("retrievalResults", [])
            if r.get("content", {}).get("text")
        ]

        return "\n\n".join(results) if results else "No relevant information found."

    except Exception as e:
        return f"Error in clinical document retrieval: {e}"
