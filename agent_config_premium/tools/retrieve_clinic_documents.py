"""Custom tool for healthcare document retrieval with clinic isolation."""
import boto3
import os
from strands import tool


@tool
def retrieve_clinic_documents(query: str, clinic_id: str, max_results: int = 5) -> str:
    """
    Handle document-based, narrative, and conceptual queries using the unstructured knowledge base.
    
    Args:
        query: A question about clinical documents, patient information, medical procedures,
               or requiring document comprehension and qualitative analysis
        clinic_id: Clinic identifier for filtering
        max_results: Number of results to return (default: 5)
    
    Returns:
        Formatted string response from the knowledge base
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID")
    
    if not kb_id:
        return "Error: Knowledge Base ID not configured. Please set KNOWLEDGE_BASE_ID environment variable."
    
    bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)
    
    try:
        retrieve_response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": max_results,
                    "filter": {"equals": {"key": "clinic_id", "value": clinic_id}}
                }
            }
        )
        
        # Format the response for better readability
        results = []
        for result in retrieve_response.get('retrievalResults', []):
            content = result.get('content', {}).get('text', '')
            if content:
                results.append(content)
        
        return "\n\n".join(results) if results else "No relevant information found."
        
    except Exception as e:
        return f"Error in clinical document retrieval: {str(e)}"
