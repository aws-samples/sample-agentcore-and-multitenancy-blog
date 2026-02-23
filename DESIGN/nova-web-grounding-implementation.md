# Nova 2 Web Grounding Implementation Guide

## Overview

This document outlines the implementation of Amazon Nova 2's built-in web grounding capability as the premium tier differentiator for the healthcare multi-tenancy demo. This approach eliminates the need for external web search APIs (Tavily, Brave Search) and Lambda functions.

Refer to https://docs.aws.amazon.com/nova/latest/nova2-userguide/web-grounding.html for sample code

## Technical Implementation

### 1. Model Configuration

**Premium Tier Agent** (`agent_config_premium/agent.py`):

```python
from strands_agents import Agent, BedrockModel

# Configure Nova 2 Lite with web grounding
model = BedrockModel(
    model_id=inference_profile_arn,  # Points to Nova 2 Lite profile
    tool_config={
        "tools": [{
            "systemTool": {
                "name": "nova_grounding"
            }
        }]
    }
)

# System prompt should mention web search capability
system_prompt = """You are a premium healthcare clinical document assistant with access to:
1. Your clinic's clinical documents via Knowledge Base search
2. External medical research and guidelines via web search
3. Structured patient and clinic data via tools

When answering questions:
- First search the clinic's documents for relevant information
- If additional context is needed, use web search for current medical guidelines
- Always cite sources with URLs for web-sourced information
- Clearly distinguish between clinic documents and external sources

You have access to web search for medical research from trusted sources like:
- NIH (nih.gov)
- CDC (cdc.gov)
- WHO (who.int)
- PubMed (pubmed.ncbi.nlm.nih.gov)
- Medical journals and .edu institutions
"""

agent = Agent(
    model=model,
    system_prompt=system_prompt,
    tools=[retrieve_tool, patient_context_tool, clinic_config_tool]
)
```

### 2. Response Structure

Nova 2 returns responses with interleaved citations:

```python
{
  "output": {
    "message": {
      "content": [
        {
          "text": "Recent quantum computing developments include...",
          "citationsContent": [
            {
              "location": {
                "web": {
                  "url": "https://example.com/quantum-news",
                  "domain": "example.com"
                }
              }
            }
          ]
        }
      ]
    }
  }
}
```

### 3. IAM Permissions

**Required Permission** (add to runtime role):

```json
{
    "Statement": [ 
        { 
            "Effect": "Allow", 
            "Action": ["bedrock:InvokeTool"], 
            "Resource": ["arn:aws:bedrock:*:*:system-tool/amazon.nova_grounding"] 
        } 
    ] 
}
```

**Note**: This permission should be added to the AgentCore runtime IAM role during infrastructure setup.

### 4. Regional Availability

**Important**: Web Grounding is currently only available in:
- US regions (us-east-1, us-west-2)
- Supported only by US CRIS profiles

**Deployment Consideration**: Ensure inference profiles are created in a US region.

## Implementation Checklist

### Phase 1: Model Configuration (Day 1) ✅ COMPLETED

- [x] **Update Inference Profile Script**
  - [x] Change premium model ID to `us.amazon.nova-2-lite-v1:0`

- [x] **Update Premium Agent Configuration**
  - [x] Add `tool_config` to BedrockModel initialization
  - [x] Include `systemTool: nova_grounding` configuration
  - [x] Update system prompt to mention web search capability

- [x] **Update IAM Permissions**
  - [x] Add `bedrock:InvokeTool` permission to runtime role
  - [x] Specify `amazon.nova_grounding` resource ARN

### Phase 2: Testing (Day 2)

- [ ] **Unit Tests**
  - [ ] Test web grounding activation
  - [ ] Verify citations in responses
  - [ ] Test fallback when web search not needed

- [ ] **Integration Tests**
  - [ ] Test with medical research queries
  - [ ] Verify source filtering (trustworthy domains)
  - [ ] Test citation formatting
  - [ ] Verify basic tier doesn't have web access

- [ ] **Demo Scenarios**
  - [ ] "What are the latest CDC guidelines for hypertension treatment?"
  - [ ] "Find recent research on diabetes management protocols"
  - [ ] "What are current WHO recommendations for vaccine schedules?"

## Demo Scenarios

### Scenario 1: Basic Tier (No Web Access)

**User**: "What are the latest CDC guidelines for hypertension?"

**Expected Response**: 
```
I can search our clinic's documents for hypertension guidelines. However, I don't have 
access to external sources like CDC. For the most current CDC guidelines, please visit 
cdc.gov directly or upgrade to Premium tier for web search capability.

Based on our clinic's documents, here's what I found...
```

### Scenario 2: Premium Tier (With Web Grounding)

**User**: "What are the latest CDC guidelines for hypertension?"

**Expected Response**:
```
Based on current CDC guidelines, hypertension management recommendations include:

1. Blood Pressure Targets: <140/90 mmHg for most adults [https://cdc.gov/bloodpressure]
2. Lifestyle Modifications: Diet, exercise, weight management [https://cdc.gov/heartdisease]
3. Medication Protocols: ACE inhibitors, ARBs, or calcium channel blockers as first-line 
   [https://cdc.gov/hypertension-treatment]

I've also checked our clinic's documents and found 3 relevant patient cases following 
these protocols...
```

### Scenario 3: Hybrid Search (Documents + Web)

**User**: "Compare our clinic's hypertension outcomes with national standards"

**Expected Response**:
```
I'll analyze both our clinic's data and national benchmarks:

**Our Clinic's Data** (from 15 patient records):
- Average BP reduction: 18/12 mmHg
- Medication adherence: 85%
- Follow-up compliance: 92%

**National Standards** [https://nih.gov/hypertension-outcomes]:
- Target BP reduction: 15/10 mmHg
- Average adherence: 75%
- Recommended follow-up: 90%

**Analysis**: Our clinic exceeds national standards in all three metrics...
```

## Error Handling

### Common Issues

**1. Permission Denied**
```
Error: User is not authorized to perform: bedrock:InvokeTool
```
**Solution**: Add `bedrock:InvokeTool` permission to runtime IAM role

**2. Region Not Supported**
```
Error: Web Grounding not available in this region
```
**Solution**: Ensure inference profile created in US region (us-east-1 or us-west-2)

**3. Tool Name Conflict**
```
Error: Tool name 'nova_grounding' conflicts with existing tool
```
**Solution**: Don't define custom tool with name `nova_grounding` - it's reserved

