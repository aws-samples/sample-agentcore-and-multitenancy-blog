# Healthcare Document Upload - Deployment Integration Plan

## Overview

Integrate healthcare document generation into `deploy.sh` so users only need to run one command. Documents are automatically generated if missing, or skipped if they already exist.

---

## User Experience

**Single command deployment**:
```bash
./deploy.sh  # Automatically generates documents if needed
```

**What happens**:
1. Checks if healthcare documents exist
2. If missing: Generates ~213 synthetic clinical documents using Claude Sonnet 4.5 (~$1.67 cost)
3. If exists: Skips generation
4. Proceeds with normal deployment (Knowledge Base upload, agent configuration, etc.)

---

## Implementation

### Step 1: Create Document Generation Script

**File**: `scripts/generate_healthcare_documents.py`

**Complete implementation available in**: [document-generation-plan.md](./document-generation-plan.md#step-1-create-document-generation-script)

**Key features**:
- Generates ~213 synthetic clinical documents across 8 clinics
- Uses Claude Sonnet 4.5 for realistic medical content
- Checks if documents exist (skips if present)
- Saves to `prerequisite/basic-documents/` and `prerequisite/premium-documents/`
- HIPAA-compliant synthetic data (no real PHI)

### Step 2: Update deploy.sh

Add document generation check after dependency installation:

```bash
# Add this section after "Installing dependencies" and before "Creating AWS infrastructure"

print_step "Checking for healthcare documents..."
if [ ! -d "prerequisite/basic-documents" ] || [ ! -d "prerequisite/premium-documents" ]; then
    print_step "Generating synthetic healthcare documents..."
    print_warning "Using Claude Sonnet 4.5 to generate ~213 clinical documents (estimated cost: ~$1.67)"
    python scripts/generate_healthcare_documents.py
    
    if [ $? -ne 0 ]; then
        print_error "Document generation failed. Check AWS credentials and Bedrock access."
        exit 1
    fi
else
    print_step "Healthcare documents found, skipping generation"
fi
```

### Step 3: Update Configuration Files

**`prerequisite/prereqs_config.yaml`**:
```yaml
knowledge_base_name: 'healthcare-basic'
knowledge_base_description: 'Clinical documents for basic tier clinics'
kb_files_path: "basic-documents"
```

**`prerequisite/premium_prereqs_config.yaml`**:
```yaml
knowledge_base_name: 'healthcare-premium'
knowledge_base_description: 'Clinical documents for premium tier clinics'
kb_files_path: "premium-documents"
```


---

## Deployment Flow

```
./deploy.sh
│
├─> Install dependencies
│
├─> 🆕 Check documents
│   ├─> Missing? → Generate with Claude Sonnet 4.5 (~213 docs)
│   └─> Exist? → Skip generation
│
├─> Create infrastructure
├─> Upload to Knowledge Base (automatic via knowledge_base.py)
├─> Configure agents
└─> Done!
```


---

## Migration Checklist

- [ ] Create `scripts/generate_healthcare_documents.py` (see Step 1)
- [ ] Update `deploy.sh` (add document generation check)
- [ ] Update `prerequisite/prereqs_config.yaml`
- [ ] Update `prerequisite/premium_prereqs_config.yaml`
- [ ] Test fresh deployment
- [ ] Test incremental deployment
- [ ] Update README.md with healthcare context

---

## Summary

**For end users**: Just run `./deploy.sh` - documents are generated automatically if needed.

**Key benefits**:
- ✅ Single command deployment
- ✅ Idempotent (safe to run multiple times)
- ✅ Smart caching (won't regenerate existing docs)
- ✅ Clear feedback at each step
- ✅ Follows existing deployment pattern

**Cost**: ~$1.67 for initial document generation (one-time, cached thereafter)
