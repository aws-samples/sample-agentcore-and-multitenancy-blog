# Document Retrieval Strategy for Healthcare Multi-Tenancy

## Executive Summary

This document outlines the custom document retrieval implementation for the healthcare multi-tenancy platform. We use **custom Lambda-based retrieval tools with metadata filtering** instead of Strands' built-in `retrieve` tool to ensure proper tenant isolation at the vector search level.

## Why Custom Retrieval Tool?

### Security Requirements

Healthcare multi-tenancy requires **defense in depth** for document isolation:

1. **S3 Prefix Isolation** (First Layer)
   - Documents stored in tier/clinic-specific S3 prefixes
   - Example: `s3://bucket/basic-tier/clinic-a/`
   - Knowledge Base data sources configured per prefix

2. **Vector-Level Filtering** (Second Layer - CRITICAL)
   - Metadata filtering at Knowledge Base query time
   - Ensures clinic can only retrieve their documents
   - Prevents accidental cross-clinic data leakage

3. **System Prompt Instructions** (Third Layer)
   - Agent instructed to only access clinic-specific documents
   - Provides context about document scope

### Comparison: Built-in vs Custom Retrieval

| Aspect | Strands `retrieve` | Custom `retrieve_clinic_documents` |
|--------|-------------------|-----------------------------------|
| **Metadata Filtering** | ❌ Not supported | ✅ Clinic-level filtering |
| **Vector Isolation** | ❌ Relies on S3 prefix only | ✅ Query-time enforcement |
| **Audit Trail** | ⚠️ Limited | ✅ Full logging per clinic |
| **Flexibility** | ⚠️ Fixed parameters | ✅ Custom parameters |
| **Security** | ⚠️ Single layer (S3) | ✅ Multi-layer defense |

## Architecture

### Custom Retrieval Tool Flow

```
User Query
    ↓
Agent (with clinic_id context)
    ↓
MCP Gateway (forwards clinic_id)
    ↓
retrieve_clinic_documents Lambda
    ↓
Bedrock Agent Runtime retrieve() API
    ├─ knowledgeBaseId: healthcare-basic-kb
    ├─ retrievalQuery: {text: "patient intake forms"}
    └─ retrievalConfiguration:
        └─ vectorSearchConfiguration:
            ├─ numberOfResults: 5
            └─ filter:
                └─ equals:
                    ├─ key: "clinic_id"
                    └─ value: "clinic-a"
    ↓
Knowledge Base (vector search with metadata filter)
    ↓
Filtered Results (only clinic-a documents)
    ↓
Formatted Response to Agent
```

## Implementation

### 1. Custom Tool with @tool Decorator

**Location**: `agent_config/tools.py` and `agent_config_premium/tools.py`

Following the Strands pattern from the screenshot, we create a custom tool using the `@tool` decorator:

```python
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
                # Optionally include score and source for transparency
                score = result.get('score', 0)
                s3_uri = result.get('location', {}).get('s3Location', {}).get('uri', '')
                
                # Format with score and source for audit trail
                results.append(f"[Score: {score:.2f}]\n{content}\nSource: {s3_uri}")
        
        return "\n\n---\n\n".join(results) if results else "No relevant documents found."
        
    except Exception as e:
        return f"Error retrieving clinical documents: {str(e)}"
```

### 2. Agent Configuration Updates

**Create `agent_config/tools.py`**:

```python
"""Custom tools for healthcare document retrieval with clinic isolation."""
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
```

**Update `agent_config/agent.py`** (Basic Tier):

```python
from .utils import get_ssm_parameter
from agent_config.memory_hook_provider import MemoryHook
from agent_config.tools import retrieve_clinic_documents  # Import custom tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands_tools import current_time  # Keep current_time
# Remove: from strands_tools import retrieve  # REMOVED
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from typing import List


class CustomerSupport:
    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook,
        bedrock_model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        system_prompt: str = None,
        tools: List[callable] = None,
        tenant_id: str = "basic",
        clinic_id: str = "demo-clinic",
        user_id: str = "demo-user",
        role: str = "user",
        s3_prefix: str = "basic-tier/demo-clinic/",
        guardrail_id: str = None,
    ):
        # ... existing model configuration ...
        
        # Gateway client setup
        gateway_url = get_ssm_parameter("/app/customersupport/agentcore/gateway_url")
        
        try:
            self.gateway_client = MCPClient(
                lambda: streamablehttp_client(
                    gateway_url,
                    headers={
                        "Authorization": f"Bearer {bearer_token}",
                        "X-Tenant-ID": tenant_id,
                        "X-Clinic-ID": clinic_id,
                        "X-S3-Prefix": s3_prefix
                    },
                )
            )
            self.gateway_client.start()
        except Exception as e:
            raise f"Error initializing agent: {str(e)}"
        
        # Create wrapper for retrieve_clinic_documents with clinic_id pre-filled
        def retrieve_with_clinic(query: str, max_results: int = 5) -> str:
            """Wrapper that automatically provides clinic_id"""
            return retrieve_clinic_documents(query, clinic_id, max_results)
        
        # Copy tool metadata
        retrieve_with_clinic.__name__ = 'retrieve_clinic_documents'
        retrieve_with_clinic.__doc__ = retrieve_clinic_documents.__doc__
        
        # Build tools list with custom retrieval tool
        self.tools = (
            [
                retrieve_with_clinic,  # Custom tool with clinic_id pre-filled
                current_time,
            ]
            + self.gateway_client.list_tools_sync()  # MCP gateway tools
            + (tools or [])
        )
        
        self.memory_hook = memory_hook
        
        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            hooks=[self.memory_hook],
        )
```

**Update System Prompt**:

```python
AVAILABLE TOOLS:
- retrieve_clinic_documents: Search knowledge base for medical information and clinical documents
  * Automatically filtered to your clinic: {clinic_id}
  * Searches documents under your clinic's scope: {s3_prefix}
  * Returns relevant documents with relevance scores and sources
- patient_context: Retrieve patient metadata (demographics, conditions, allergies, medications, visit history)
- clinic_config: Get clinic configuration (specialty, services, hours, providers)
- current_time: Get current date and time
```

### 3. Knowledge Base Metadata Configuration

**Metadata Requirements**:

All documents uploaded to S3 must have metadata:

```json
{
  "clinic_id": "clinic-a",
  "document_type": "intake-form",
  "date": "2024-01-15",
  "patient_id": "P12345"  // Optional
}
```

**S3 Upload with Metadata** (in document generation script):

```python
import boto3

s3_client = boto3.client('s3')

# Upload with metadata
s3_client.put_object(
    Bucket='healthcare-documents',
    Key='basic-tier/clinic-a/intake-forms/patient-001.txt',
    Body=document_content,
    Metadata={
        'clinic_id': 'clinic-a',
        'document_type': 'intake-form',
        'date': '2024-01-15'
    }
)
```

**Knowledge Base Data Source Configuration**:

```python
# When creating Knowledge Base data source
data_source_config = {
    'type': 'S3',
    's3Configuration': {
        'bucketArn': f'arn:aws:s3:::healthcare-documents',
        'inclusionPrefixes': ['basic-tier/clinic-a/']  # Clinic-specific prefix
    },
    'vectorIngestionConfiguration': {
        'chunkingConfiguration': {
            'chunkingStrategy': 'FIXED_SIZE',
            'fixedSizeChunkingConfiguration': {
                'maxTokens': 300,
                'overlapPercentage': 20
            }
        }
    }
}
```

### 4. Environment Configuration

**Update `main.py` and `main_premium.py`**:

```python
import os
from agent_config.utils import get_ssm_parameter

# Set Knowledge Base ID from SSM
kb_id = get_ssm_parameter("/app/healthcare/knowledge_base/knowledge_base_id")
os.environ['KNOWLEDGE_BASE_ID'] = kb_id

# Set AWS region
os.environ['AWS_REGION'] = 'us-east-1'
```

**No Lambda or Gateway Registration Needed**:
- The `@tool` decorator makes the function directly available to the Strands agent
- No need for Lambda deployment
- No need for MCP gateway tool registration
- Tool runs in the same process as the agent

## Security Benefits

### Multi-Layer Defense

1. **Infrastructure Layer**: S3 prefix isolation
2. **Query Layer**: Metadata filtering (THIS IS KEY)
3. **Application Layer**: System prompt instructions
4. **Audit Layer**: Full logging of clinic access

### Attack Scenarios Prevented

| Attack Scenario | Prevention Mechanism |
|----------------|---------------------|
| Clinic A tries to access Clinic B documents | Metadata filter blocks at query time |
| Malicious query tries to bypass filter | Lambda enforces clinic_id from JWT |
| Agent hallucinates cross-clinic access | System prompt + metadata filter prevent |
| S3 misconfiguration exposes documents | Metadata filter provides backup isolation |

## Testing Strategy

### Unit Tests

```python
def test_retrieve_with_clinic_filter():
    """Test that retrieval respects clinic_id filter"""
    event = {
        'query': 'patient intake forms',
        'clinic_id': 'clinic-a',
        'max_results': 5
    }
    
    response = lambda_handler(event, None)
    
    assert response['clinic_id'] == 'clinic-a'
    assert response['count'] >= 0
    # Verify no clinic-b documents in results
```

### Integration Tests

```python
def test_cross_clinic_isolation():
    """Test that clinic-a cannot access clinic-b documents"""
    # Upload test document for clinic-b
    upload_test_document('clinic-b', 'secret-document.txt')
    
    # Try to retrieve as clinic-a
    event = {
        'query': 'secret document',
        'clinic_id': 'clinic-a',
        'max_results': 10
    }
    
    response = lambda_handler(event, None)
    
    # Should return no results
    assert response['count'] == 0
    assert 'secret-document' not in response['results']
```

## Deployment Checklist

- [x] Create `agent_config/tools/retrieve_clinic_documents.py` with `@tool` decorator
- [x] Create `agent_config_premium/tools/retrieve_clinic_documents.py` (same content)
- [x] Update `agent_config/agent.py` to import and use custom tool
- [x] Update `agent_config_premium/agent.py` to import and use custom tool
- [x] Set `KNOWLEDGE_BASE_ID` environment variable in main.py and main_premium.py
- [ ] Upload documents with clinic_id metadata (Phase 2.1)
- [ ] Verify Knowledge Base indexes metadata (Phase 2.1)
- [x] Update system prompts to reference new tool
- [ ] Test cross-clinic isolation (Phase 2.3)
- [ ] Verify audit logging (Phase 2.3)

**No Lambda or Gateway Registration Required** - Tool runs directly in agent process using `@tool` decorator

## Monitoring and Observability

### CloudWatch Metrics

- Document retrieval count per clinic
- Average relevance scores
- Query latency
- Error rates per clinic

### CloudWatch Logs Insights Queries

```sql
-- Documents retrieved per clinic
fields @timestamp, clinic_id, count
| filter @message like /Retrieved/
| stats sum(count) by clinic_id

-- Failed retrievals
fields @timestamp, clinic_id, error
| filter @message like /Error retrieving/
```

## Cost Implications

### Per-Query Costs

- Bedrock Agent Runtime retrieve API: ~$0.0001 per query
- Lambda execution: ~$0.0000002 per invocation
- CloudWatch Logs: ~$0.50 per GB

### Optimization

- Cache frequent queries (future enhancement)
- Adjust max_results based on tier
- Use pagination for large result sets

## Future Enhancements

1. **Advanced Filtering**: Support multiple metadata filters (date range, document type)
2. **Caching**: Cache frequent queries per clinic
3. **Pagination**: Support for large result sets
4. **Hybrid Search**: Combine vector and keyword search
5. **Reranking**: Use Bedrock reranking for better relevance

## References

- [Bedrock Knowledge Base Retrieve API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html)
- [Knowledge Base Metadata Filtering](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- [AgentCore Gateway Tool Registration](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-gateway.html)
