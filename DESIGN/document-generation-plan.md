# Clinical Document Generation Plan

## Overview

This document outlines the strategy for generating synthetic clinical documents for the healthcare multi-tenant demo. Documents will be created using LLMs to generate realistic but synthetic (HIPAA-compliant) clinical content, then organized according to the S3 structure defined in `technical-architecture.md`.

---

## Document Storage Structure

Following the structure from `technical-architecture.md`:

```
s3://healthcare-documents/
├── basic-tier/
│   ├── clinic-a/          # Family Practice
│   │   ├── patient-intake/
│   │   ├── appointment-notes/
│   │   ├── lab-results/
│   │   └── prescriptions/
│   ├── clinic-b/          # Urgent Care
│   │   ├── patient-intake/
│   │   ├── injury-reports/
│   │   ├── diagnostic-notes/
│   │   └── discharge-instructions/
│   ├── clinic-c/          # Pediatrics
│   │   ├── well-child-visits/
│   │   ├── vaccination-records/
│   │   ├── sick-visit-notes/
│   │   └── growth-charts/
│   └── clinic-d/          # Internal Medicine
│       ├── chronic-disease-notes/
│       ├── annual-physicals/
│       ├── lab-results/
│       └── specialist-referrals/
└── premium-tier/
    ├── hospital-a/        # Multi-Specialty Hospital
    │   ├── diagnostic-reports/
    │   ├── imaging-studies/
    │   ├── pathology-reports/
    │   ├── surgical-notes/
    │   └── specialist-consultations/
    ├── clinic-e/          # Cardiology
    │   ├── catheterization-reports/
    │   ├── echocardiogram-reports/
    │   ├── stress-test-results/
    │   ├── holter-monitor-reports/
    │   └── cardiac-imaging/
    ├── clinic-f/          # Oncology
    │   ├── pathology-reports/
    │   ├── imaging-studies/
    │   ├── treatment-plans/
    │   ├── clinical-trial-docs/
    │   └── genomic-testing/
    └── hospital-b/        # Academic Medical Center
        ├── admission-notes/
        ├── progress-notes/
        ├── procedure-notes/
        ├── discharge-summaries/
        ├── teaching-cases/
        └── research-data/
```

---

## Phase 2.1 Implementation: Document Generation (Week 1, Days 1-5)

### Step 1: Create Document Generation Script

**Script**: `scripts/generate_sample_documents.py`


**Key Features**:
- Use Bedrock LLM (Claude or Nova) to generate realistic clinical content
- Ensure all PHI is synthetic (no real patient data)
- Generate documents with appropriate medical terminology
- Include realistic dates, measurements, and clinical findings
- Create variety within each document type

**Complete Implementation**:

See the complete script in `scripts/generate_healthcare_documents.py`:

```python
#!/usr/bin/env python3
"""
Generate synthetic healthcare documents for multi-tenant demo.
This script generates ~213 clinical documents across 8 clinics.
"""

import boto3
import json
import os
from datetime import datetime, timedelta
import random
from pathlib import Path

# Configuration
BASIC_CLINICS = {
    'clinic-a': {
        'specialty': 'Family Practice',
        'document_types': ['patient-intake', 'appointment-notes', 'lab-results', 'prescriptions'],
        'count_per_type': 2  
    },
    'clinic-b': {
        'specialty': 'Urgent Care',
        'document_types': ['patient-intake', 'injury-reports', 'diagnostic-notes', 'discharge-instructions'],
        'count_per_type': 2  
    },
    'clinic-c': {
        'specialty': 'Pediatrics',
        'document_types': ['well-child-visits', 'vaccination-records', 'sick-visit-notes', 'growth-charts'],
        'count_per_type': 2  
    },
    'clinic-d': {
        'specialty': 'Internal Medicine',
        'document_types': ['chronic-disease-notes', 'annual-physicals', 'lab-results', 'specialist-referrals'],
        'count_per_type': 2  
    }
}

PREMIUM_CLINICS = {
    'hospital-a': {
        'specialty': 'Multi-Specialty Hospital',
        'document_types': ['diagnostic-reports', 'imaging-studies', 'pathology-reports', 
                          'surgical-notes', 'specialist-consultations', 'research-data'],
        'count_per_type': 2  
    },
    'clinic-e': {
        'specialty': 'Cardiology',
        'document_types': ['catheterization-reports', 'echocardiogram-reports', 'stress-test-results',
                          'holter-monitor-reports', 'cardiac-imaging'],
        'count_per_type': 2  
    },
    'clinic-f': {
        'specialty': 'Oncology',
        'document_types': ['pathology-reports', 'imaging-studies', 'treatment-plans',
                          'clinical-trial-docs', 'tumor-board-notes', 'genomic-testing'],
        'count_per_type': 2 
    },
    'hospital-b': {
        'specialty': 'Academic Medical Center',
        'document_types': ['admission-notes', 'progress-notes', 'procedure-notes',
                          'discharge-summaries', 'teaching-cases', 'research-data', 'imaging-studies'],
        'count_per_type': 2  
    }
}

def check_documents_exist():
    """Check if healthcare documents already exist"""
    basic_path = Path('prerequisite/basic-documents')
    premium_path = Path('prerequisite/premium-documents')
    
    basic_exists = basic_path.exists() and any(basic_path.rglob('*.txt'))
    premium_exists = premium_path.exists() and any(premium_path.rglob('*.txt'))
    
    return basic_exists and premium_exists

def generate_clinical_document(document_type, clinic_specialty, bedrock_client):
    """Generate a synthetic clinical document using Claude Sonnet 4.5"""
    
    prompts = {
        'patient-intake': f"""Generate a realistic but synthetic patient intake form for a {clinic_specialty} clinic.
Include: patient demographics (synthetic), chief complaint, medical history, current medications, allergies.
Use realistic medical terminology. Ensure all data is completely synthetic (no real PHI).
Format as a structured clinical document. Keep it concise (200-400 words).""",
        
        'appointment-notes': f"""Generate a realistic but synthetic appointment note for a {clinic_specialty} visit.
Include: chief complaint, history of present illness, physical exam findings, assessment, plan.
Use SOAP note format. All data must be synthetic. Keep it concise (200-400 words).""",
        
        'lab-results': f"""Generate realistic but synthetic lab results appropriate for {clinic_specialty}.
Include: test names, values, reference ranges, interpretation notes.
Use common lab panels. All data must be synthetic. Keep it concise (200-400 words).""",
    }
    
    # Use generic prompt for document types not in the dictionary
    prompt = prompts.get(document_type, f"""Generate a realistic but synthetic {document_type.replace('-', ' ')} 
for a {clinic_specialty} clinic. Use realistic medical terminology. Ensure all data is completely synthetic (no real PHI).
Keep it concise (200-400 words).""")
    
    try:
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-sonnet-4-v2:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
    except Exception as e:
        print(f"⚠️  Error generating document: {e}")
        return f"""SYNTHETIC CLINICAL DOCUMENT - {document_type.upper()}

Clinic Specialty: {clinic_specialty}
Date: {datetime.now().strftime('%Y-%m-%d')}

This is a synthetic clinical document generated for demonstration purposes.
All patient information is completely fictional and does not represent real individuals.

[Document content would appear here in a production system]
"""

def generate_documents_for_clinic(clinic_id, tier, specialty, document_types, count_per_type, bedrock_client):
    """Generate all documents for a specific clinic"""
    
    documents = []
    
    for doc_type in document_types:
        print(f"  Generating {count_per_type} {doc_type} documents...")
        for i in range(count_per_type):
            content = generate_clinical_document(doc_type, specialty, bedrock_client)
            doc_date = datetime.now() - timedelta(days=random.randint(1, 90))
            
            document = {
                'clinic_id': clinic_id,
                'tier': tier,
                'document_type': doc_type,
                'content': content,
                'date': doc_date.isoformat(),
                'filename': f"{doc_type}_{doc_date.strftime('%Y%m%d')}_{i+1:03d}.txt"
            }
            
            documents.append(document)
    
    return documents

def save_documents_locally(documents, base_path):
    """Save generated documents to local filesystem"""
    
    for doc in documents:
        doc_dir = Path(base_path) / doc['tier'] / doc['clinic_id'] / doc['document_type']
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        doc_path = doc_dir / doc['filename']
        with open(doc_path, 'w') as f:
            f.write(doc['content'])

def main():
    print("🏥 Healthcare Document Generation")
    print("=" * 60)
    
    if check_documents_exist():
        print("✅ Healthcare documents already exist. Skipping generation.")
        return
    
    print("📝 Generating ~80 synthetic clinical documents...")
    print("   Using Claude Sonnet 4.5 (estimated cost: ~$0.63)")
    
    try:
        bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    except Exception as e:
        print(f"❌ Error initializing Bedrock client: {e}")
        return
    
    all_documents = []
    
    # Generate Basic Tier documents
    print("\n📁 Generating Basic Tier documents...")
    for clinic_id, config in BASIC_CLINICS.items():
        print(f"  🏥 {clinic_id} ({config['specialty']})...")
        docs = generate_documents_for_clinic(
            clinic_id=clinic_id,
            tier='basic-tier',
            specialty=config['specialty'],
            document_types=config['document_types'],
            count_per_type=config['count_per_type'],
            bedrock_client=bedrock_client
        )
        all_documents.extend(docs)
    
    # Generate Premium Tier documents
    print("\n📁 Generating Premium Tier documents...")
    for clinic_id, config in PREMIUM_CLINICS.items():
        print(f"  🏥 {clinic_id} ({config['specialty']})...")
        docs = generate_documents_for_clinic(
            clinic_id=clinic_id,
            tier='premium-tier',
            specialty=config['specialty'],
            document_types=config['document_types'],
            count_per_type=config['count_per_type'],
            bedrock_client=bedrock_client
        )
        all_documents.extend(docs)
    
    # Save documents
    print(f"\n💾 Saving {len(all_documents)} documents...")
    Path('prerequisite/basic-documents').mkdir(parents=True, exist_ok=True)
    Path('prerequisite/premium-documents').mkdir(parents=True, exist_ok=True)
    
    basic_docs = [d for d in all_documents if d['tier'] == 'basic-tier']
    premium_docs = [d for d in all_documents if d['tier'] == 'premium-tier']
    
    save_documents_locally(basic_docs, 'prerequisite/basic-documents')
    save_documents_locally(premium_docs, 'prerequisite/premium-documents')
    
    print("\n✅ Document generation complete!")
    print(f"   Total: {len(all_documents)} documents")
    print(f"   Basic tier: {len(basic_docs)} | Premium tier: {len(premium_docs)}")

if __name__ == '__main__':
    main()
```

### Step 2: Document Templates by Clinic

#### Basic Tier Document Templates (8 documents per clinic)

**Clinic A (Family Practice) - 8 documents**:
- 2 Patient Intake Forms
- 2 Appointment Notes
- 2 Lab Results (CBC, metabolic panel, urinalysis)
- 2 Prescriptions

**Clinic B (Urgent Care) - 8 documents**:
- 2 Patient Intake Forms (rapid triage)
- 2 Injury Reports (lacerations, sprains, fractures)
- 2 Diagnostic Notes
- 2 Discharge Instructions

**Clinic C (Pediatrics) - 8 documents**:
- 2 Well-Child Visit Notes
- 2 Vaccination Records
- 2 Sick Visit Notes
- 2 Growth Charts

**Clinic D (Internal Medicine) - 8 documents**:
- 2 Chronic Disease Management Notes
- 2 Annual Physical Exams
- 2 Lab Results (lipid panels, A1C, thyroid)
- 2 Specialist Referrals

**Basic Tier Total**: ~32 documents

#### Premium Tier Document Templates (10-14 documents per clinic)

**Hospital A (Multi-Specialty) - 12 documents**:
- 2 Diagnostic Reports (cardiac cath, stress tests)
- 2 Imaging Studies (CT, MRI, PET scans)
- 2 Pathology Reports
- 2 Surgical Notes
- 2 Specialist Consultations
- 2 Research Data

**Clinic E (Cardiology) - 10 documents**:
- 2 Cardiac Catheterization Reports
- 2 Echocardiogram Reports
- 2 Stress Test Results
- 2 Holter Monitor Reports
- 2 Cardiac Imaging (MRI/CT)

**Clinic F (Oncology) - 12 documents**:
- 2 Pathology Reports (tumor histology, molecular markers)
- 2 Imaging Studies (staging, response assessment)
- 2 Treatment Plans
- 2 Clinical Trial Documents
- 2 Tumor Board Notes
- 2 Genomic Testing Reports

**Hospital B (Academic Medical Center) - 14 documents**:
- 2 Admission Notes
- 2 Progress Notes
- 2 Procedure Notes
- 2 Discharge Summaries
- 2 Teaching Case Presentations
- 2 Research Data
- 2 Imaging Studies

**Premium Tier Total**: ~48 documents

**Grand Total**: ~80 documents across 8 clinics

### Step 3: Document Upload Script

**Script**: `scripts/upload_documents_to_s3.py`

```python
import boto3
import os
from pathlib import Path

s3 = boto3.client('s3')
BUCKET_NAME = 'healthcare-documents-{account-id}'

def upload_document_to_s3(document, bucket_name):
    """Upload a single document to S3 with proper prefix"""
    
    # Construct S3 key following technical-architecture.md structure
    s3_key = f"{document['tier']}-tier/{document['clinic_id']}/{document['document_type']}/{document['filename']}"
    
    # Upload document
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=document['content'],
        Metadata={
            'clinic_id': document['clinic_id'],
            'tier': document['tier'],
            'document_type': document['document_type'],
            'date': document['date']
        },
        ContentType='text/plain'
    )
    
    print(f"✅ Uploaded: {s3_key}")
    return s3_key

def upload_all_documents(documents, bucket_name):
    """Upload all generated documents to S3"""
    
    uploaded_keys = []
    
    for doc in documents:
        try:
            key = upload_document_to_s3(doc, bucket_name)
            uploaded_keys.append(key)
        except Exception as e:
            print(f"❌ Failed to upload {doc['filename']}: {e}")
    
    return uploaded_keys

# Create document inventory
def create_document_inventory(uploaded_keys, clinic_id):
    """Create manifest of uploaded documents"""
    
    inventory = {
        'clinic_id': clinic_id,
        'total_documents': len(uploaded_keys),
        'upload_date': datetime.now().isoformat(),
        'documents': uploaded_keys
    }
    
    # Save inventory
    inventory_key = f"inventories/{clinic_id}_inventory.json"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=inventory_key,
        Body=json.dumps(inventory, indent=2),
        ContentType='application/json'
    )
    
    return inventory
```

### Step 4: Local Document Storage (Alternative to S3)

For development and testing, documents can also be stored locally in the `prerequisite/` folder structure:

```
prerequisite/
├── basic-documents/  (replaces 'policies')
│   ├── clinic-a/
│   │   ├── patient-intake/
│   │   │   ├── intake_20241201_001.txt
│   │   │   └── intake_20241215_002.txt
│   │   ├── appointment-notes/
│   │   ├── lab-results/
│   │   └── prescriptions/
│   ├── clinic-b/
│   ├── clinic-c/
│   └── clinic-d/
└── premium-documents/  (replaces 'premium-policies')
    ├── hospital-a/
    │   ├── diagnostic-reports/
    │   ├── imaging-studies/
    │   ├── pathology-reports/
    │   ├── surgical-notes/
    │   └── specialist-consultations/
    ├── clinic-e/
    ├── clinic-f/
    └── hospital-b/
```

**Note**: This mirrors the S3 structure and can be used for:
- Local development and testing
- Knowledge Base ingestion (if using Bedrock Knowledge Bases)
- Version control of sample documents

---

## Document Content Guidelines

### HIPAA Compliance for Synthetic Data

All generated documents MUST:
- ✅ Use completely synthetic patient names (e.g., "John Doe", "Jane Smith")
- ✅ Use synthetic dates (within last 90 days for realism)
- ✅ Use synthetic addresses, phone numbers, MRNs
- ✅ Include realistic medical terminology and findings
- ✅ Follow standard clinical documentation formats
- ❌ Never include real patient information
- ❌ Never use real provider names (use synthetic: "Dr. Smith", "Dr. Johnson")
- ❌ Never include real facility identifiers

### Document Quality Standards

Each document should:
- Be 200-1000 words (appropriate for document type)
- Include realistic medical terminology
- Follow standard clinical documentation formats (SOAP notes, etc.)
- Include appropriate measurements and values
- Have consistent patient identifiers within a clinic
- Include realistic dates and timestamps

### Example Document Snippets

**Patient Intake Form (Basic Tier)**:
```
PATIENT INTAKE FORM - FAMILY PRACTICE MEDICAL CENTER

Date: 2024-12-15
Patient Name: John Doe
Date of Birth: 1975-03-22
MRN: FA-2024-001

Chief Complaint: Annual physical examination

Medical History:
- Hypertension (diagnosed 2018)
- Type 2 Diabetes (diagnosed 2020)
- Hyperlipidemia

Current Medications:
- Lisinopril 10mg daily
- Metformin 1000mg twice daily
- Atorvastatin 20mg daily

Allergies: Penicillin (rash)

Social History: Non-smoker, occasional alcohol use
```

**Cardiac Catheterization Report (Premium Tier)**:
```
CARDIAC CATHETERIZATION REPORT

Patient: Jane Smith
MRN: HA-2024-042
Date of Procedure: 2024-12-10
Attending Physician: Dr. Anderson

Indication: Chest pain, abnormal stress test

Procedure: Left heart catheterization with coronary angiography

Findings:
- Left Main: No significant disease
- LAD: 70% stenosis in mid-segment
- LCx: 40% stenosis in proximal segment
- RCA: Dominant, no significant disease

Left Ventricular Function: EF 55%, normal wall motion

Impression: Single-vessel coronary artery disease (LAD)

Recommendation: PCI to LAD lesion vs. medical management
```

---

## Implementation Timeline (Phase 2.1)

### Day 1-2: Script Development
- [ ] Create `generate_sample_documents.py`
- [ ] Create `upload_documents_to_s3.py`
- [ ] Test document generation with 2-3 sample documents
- [ ] Verify HIPAA compliance of synthetic data

### Day 3: Basic Tier Document Generation
- [ ] Generate documents for Clinic A (8 docs)
- [ ] Generate documents for Clinic B (8 docs)
- [ ] Generate documents for Clinic C (8 docs)
- [ ] Generate documents for Clinic D (8 docs)
- [ ] Total: ~32 documents

### Day 4: Premium Tier Document Generation
- [ ] Generate documents for Hospital A (12 docs)
- [ ] Generate documents for Clinic E (10 docs)
- [ ] Generate documents for Clinic F (12 docs)
- [ ] Generate documents for Hospital B (14 docs)
- [ ] Total: ~48 documents

### Day 5: Upload and Verification
- [ ] Upload all documents to S3 with proper prefixes
- [ ] Create document inventories per clinic
- [ ] Verify folder structure matches technical-architecture.md
- [ ] Test document retrieval with S3 prefix filtering
- [ ] Create sample queries for each clinic

---

## Knowledge Base Integration (Optional)

If using Bedrock Knowledge Bases for document search:

### Step 1: Create Knowledge Bases
```python
# Create 2 Knowledge Bases (basic-tier, premium-tier)
import boto3

bedrock_agent = boto3.client('bedrock-agent')

# Basic tier KB
basic_kb = bedrock_agent.create_knowledge_base(
    name='healthcare-basic-kb',
    description='Clinical documents for basic tier clinics',
    roleArn='arn:aws:iam::ACCOUNT:role/BedrockKBRole',
    knowledgeBaseConfiguration={
        'type': 'VECTOR',
        'vectorKnowledgeBaseConfiguration': {
            'embeddingModelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1'
        }
    },
    storageConfiguration={
        'type': 'OPENSEARCH_SERVERLESS',
        'opensearchServerlessConfiguration': {
            'collectionArn': 'arn:aws:aoss:us-east-1:ACCOUNT:collection/basic-kb',
            'vectorIndexName': 'healthcare-basic-index',
            'fieldMapping': {
                'vectorField': 'embedding',
                'textField': 'text',
                'metadataField': 'metadata'
            }
        }
    }
)

# Premium tier KB (similar structure)
```

### Step 2: Create Data Sources
```python
# Add S3 data source with clinic-specific prefixes
basic_kb_ds = bedrock_agent.create_data_source(
    knowledgeBaseId=basic_kb['knowledgeBase']['knowledgeBaseId'],
    name='basic-tier-documents',
    dataSourceConfiguration={
        'type': 'S3',
        's3Configuration': {
            'bucketArn': f'arn:aws:s3:::healthcare-documents-{account_id}',
            'inclusionPrefixes': [
                'basic-tier/clinic-a/',
                'basic-tier/clinic-b/',
                'basic-tier/clinic-c/',
                'basic-tier/clinic-d/'
            ]
        }
    }
)

# Sync documents
bedrock_agent.start_ingestion_job(
    knowledgeBaseId=basic_kb['knowledgeBase']['knowledgeBaseId'],
    dataSourceId=basic_kb_ds['dataSource']['dataSourceId']
)
```

---

## Testing and Validation

### Document Quality Checks
- [ ] Verify all documents contain synthetic data only
- [ ] Check medical terminology accuracy
- [ ] Validate document format consistency
- [ ] Ensure appropriate document length
- [ ] Verify date ranges are realistic

### S3 Structure Validation
- [ ] Confirm folder structure matches technical-architecture.md
- [ ] Verify S3 prefixes enable clinic isolation
- [ ] Test document retrieval with prefix filtering
- [ ] Validate metadata tags on all documents

### Sample Queries for Testing
```python
# Test queries per clinic
test_queries = {
    'clinic-a': "Show me recent patient intake forms",
    'clinic-b': "List all injury reports from this week",
    'clinic-c': "Find vaccination records for 2-year-olds",
    'clinic-d': "Show diabetes patients with recent A1C results",
    'hospital-a': "Analyze cardiac catheterization trends",
    'clinic-e': "Compare echocardiogram results with stress tests",
    'clinic-f': "Show all breast cancer patients with HER2+ status",
    'hospital-b': "Generate summary of ICU admissions this month"
}
```

---

## Deliverables

1. **Document Generation Script**: `scripts/generate_sample_documents.py`
2. **Upload Script**: `scripts/upload_documents_to_s3.py`
3. **~213 Synthetic Clinical Documents** across 8 clinics (20-30 per clinic)
4. **Document Inventories**: JSON manifests per clinic
5. **S3 Bucket Structure**: Matching technical-architecture.md
6. **Sample Queries**: Test queries for each clinic
7. **Validation Report**: Document quality and structure verification

---

## Cost Estimation

### Document Generation Costs
- Using Claude Sonnet 4.5 (global.anthropic.claude-sonnet-4-5-20250929-v1:0) for generation
- ~80 documents × 500 tokens/doc = 40K tokens output
- Input: 80 prompts × 100 tokens = 8K tokens
- Output: 80 docs × 500 tokens = 40K tokens
- Total: ~48K tokens
- Cost: Input (8K × $0.003/1K) + Output (40K × $0.015/1K) ≈ $0.02 + $0.60 = **$0.62**

### S3 Storage Costs
- ~80 documents × 2KB average = ~160KB
- S3 Standard: $0.023/GB/month
- Monthly cost: <$0.01

**Total Phase 2.1 Cost**: ~$0.63

---

## Next Steps

After completing Phase 2.1:
1. **Phase 2.2**: Implement clinical document tools (search, retrieval, summarization)
2. **Phase 2.3**: Integrate tools with MCP gateway
3. **Phase 2.4**: Refactor agents for healthcare domain
4. **Phase 4.2**: Create demo scenarios using generated documents
