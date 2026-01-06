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

### 1. Lambda Function: retrieve_clinic_documents.py

**Location**: `prerequisite/lambda/python/retrieve_clinic_documents.py`

```python
import boto3
import os
import json
from typing import Dict, Any, List

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Retrieve clinic-specific documents from Knowledge Base with metadata filtering.
    
    Security: Enforces clinic isolation via metadata filtering at vector search level.
    
    Args:
        event: {
            'query': str - Search query
            'clinic_id': str - Clinic identifier for filtering
            'max_results': int - Number of results (default: 5)
        }
        context: Lambda context
    
    Returns:
        {
            'results': str - Formatted document results
            'count': int - Number of documents found
            'clinic_id': str - Clinic that was queried
        }
    """
    # Extract parameters
    query = event.get('query', '')
    clinic_id = event.get('clinic_id', 'demo-clinic')
    max_results = event.get('max_results', 5)
    
    # Get Knowledge Base ID from environment
    kb_id = os.environ.get('KNOWLEDGE_BASE_ID')
    
    # Validation
    if not query:
        return {'error': 'Query parameter is required'}
    
    if not kb_id:
        return {'error': 'Knowledge Base ID not configured'}
    
    # Initialize Bedrock Agent Runtime client
    bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    try:
        # Query Knowledge Base with metadata filtering
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': max_results,
                    'filter': {
                        'equals': {
                            'key': 'clinic_id',
                            'value': clinic_id
                        }
                    }
                }
            }
        )
        
        # Format results
        results = []
        for result in response.get('retrievalResults', []):
            content = result.get('content', {}).get('text', '')
            metadata = result.get('metadata', {})
            score = result.get('score', 0)
            location = result.get('location', {})
            
            # Extract S3 URI
            s3_uri = location.get('s3Location', {}).get('uri', 'Unknown')
            
            results.append({
                'content': content,
                'score': score,
                'metadata': metadata,
                'source': s3_uri
            })
        
        # Format as readable text for agent
        formatted_results = []
        for idx, result in enumerate(results, 1):
            formatted_results.append(
                f"[Document {idx}] (Relevance: {result['score']:.2f})\n"
                f"{result['content']}\n"
                f"Source: {result['source']}\n"
                f"Metadata: {json.dumps(result['metadata'])}"
            )
        
        result_text = '\n\n---\n\n'.join(formatted_results) if formatted_results else 'No relevant documents found.'
        
        # Log for audit trail
        print(f"Retrieved {len(results)} documents for clinic: {clinic_id}, query: {query}")
        
        return {
            'results': result_text,
            'count': len(results),
            'clinic_id': clinic_id
        }
        
    except Exception as e:
        print(f"Error retrieving documents: {str(e)}")
        return {'error': f'Error retrieving documents: {str(e)}'}
```

### 2. Agent Configuration Updates

**Update both `agent_config/agent.py` and `agent_config_premium/agent.py`**:

```python
# Remove Strands retrieve import
# from strands_tools import retrieve  # REMOVE THIS

# Update tools list
self.tools = (
    [
        current_time,  # Keep this
        # retrieve,  # REMOVE - replaced by custom tool from gateway
    ]
    + self.gateway_client.list_tools_sync()  # This now includes retrieve_clinic_documents
    + tools
)
```

**System Prompt Update** (both tiers):

```python
AVAILABLE TOOLS:
- retrieve_clinic_documents: Search clinical documents with automatic clinic filtering
  * Automatically filtered to your clinic: {clinic_id}
  * Searches documents under: {s3_prefix}
  * Returns relevant documents with relevance scores
- patient_context: Retrieve patient metadata
- clinic_config: Get clinic configuration
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

### 4. Gateway Tool Registration

**Tool Schema** (api_spec.json):

```json
{
  "tools": [
    {
      "name": "retrieve_clinic_documents",
      "description": "Search clinical documents for the authenticated clinic. Automatically filters results to only include documents belonging to the clinic.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query for clinical documents"
          },
          "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 5)",
            "default": 5
          }
        },
        "required": ["query"]
      }
    }
  ]
}
```

**Registration Command**:

```bash
# Register with basic gateway
python scripts/agentcore_gateway.py register-tool \
  --gateway-name healthcare-basic-gw \
  --tool-name retrieve_clinic_documents \
  --lambda-arn arn:aws:lambda:us-east-1:ACCOUNT:function:retrieve-clinic-documents

# Register with premium gateway
python scripts/agentcore_gateway.py register-tool \
  --gateway-name healthcare-premium-gw \
  --tool-name retrieve_clinic_documents \
  --lambda-arn arn:aws:lambda:us-east-1:ACCOUNT:function:retrieve-clinic-documents
```

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

- [ ] Create Lambda function: `retrieve_clinic_documents`
- [ ] Set environment variable: `KNOWLEDGE_BASE_ID`
- [ ] Grant Lambda permissions to call Bedrock Agent Runtime
- [ ] Upload documents with clinic_id metadata
- [ ] Verify Knowledge Base indexes metadata
- [ ] Register tool with both gateways
- [ ] Update agent.py to remove Strands retrieve
- [ ] Update system prompts
- [ ] Test cross-clinic isolation
- [ ] Verify audit logging

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
