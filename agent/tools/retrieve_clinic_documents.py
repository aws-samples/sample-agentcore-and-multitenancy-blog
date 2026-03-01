"""Knowledge Base retrieval with clinic-level metadata filtering for tenant isolation."""

import boto3
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from strands import tool

EASTERN = ZoneInfo("America/New_York")
BUSINESS_HOUR_START = 8
BUSINESS_HOUR_END = 18


@tool
def retrieve_clinic_documents(query: str, clinic_id: str, max_results: int = 5) -> str:
    """
    Search the knowledge base for clinical documents, filtered to the requesting clinic.

    Tenant isolation is enforced via a metadata filter on clinic_id — each clinic
    can only retrieve documents tagged with their own identifier.

    Access is restricted to business hours (8 AM – 6 PM Eastern) to align with
    the gateway policy on patient_context.

    Args:
        query: Question about clinical documents, patient information, or medical procedures.
        clinic_id: Clinic identifier for metadata filtering.
        max_results: Number of results to return (default: 5).

    Returns:
        Formatted string with matching document content.
    """
    # Enforce business hours — same window as the Cedar policy on patient_context
    current_hour = datetime.now(EASTERN).hour
    if not (BUSINESS_HOUR_START <= current_hour < BUSINESS_HOUR_END):
        return (
            "🛡️ Access denied by business hours policy. "
            "Clinical documents are only available between 8:00 AM and 6:00 PM Eastern. "
            "Please try again during business hours."
        )

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
