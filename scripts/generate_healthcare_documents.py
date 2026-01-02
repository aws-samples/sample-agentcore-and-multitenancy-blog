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
        'count_per_type': 6  # 24 total
    },
    'clinic-b': {
        'specialty': 'Urgent Care',
        'document_types': ['patient-intake', 'injury-reports', 'diagnostic-notes', 'discharge-instructions'],
        'count_per_type': 7  # 28 total
    },
    'clinic-c': {
        'specialty': 'Pediatrics',
        'document_types': ['well-child-visits', 'vaccination-records', 'sick-visit-notes', 'growth-charts'],
        'count_per_type': 6  # 24 total
    },
    'clinic-d': {
        'specialty': 'Internal Medicine',
        'document_types': ['chronic-disease-notes', 'annual-physicals', 'lab-results', 'specialist-referrals'],
        'count_per_type': 6  # 24 total
    }
}

PREMIUM_CLINICS = {
    'hospital-a': {
        'specialty': 'Multi-Specialty Hospital',
        'document_types': ['diagnostic-reports', 'imaging-studies', 'pathology-reports', 
                          'surgical-notes', 'specialist-consultations', 'research-data'],
        'count_per_type': 5  # 30 total
    },
    'clinic-e': {
        'specialty': 'Cardiology',
        'document_types': ['catheterization-reports', 'echocardiogram-reports', 'stress-test-results',
                          'holter-monitor-reports', 'cardiac-imaging'],
        'count_per_type': 5  # 25 total
    },
    'clinic-f': {
        'specialty': 'Oncology',
        'document_types': ['pathology-reports', 'imaging-studies', 'treatment-plans',
                          'clinical-trial-docs', 'tumor-board-notes', 'genomic-testing'],
        'count_per_type': 5  # 30 total
    },
    'hospital-b': {
        'specialty': 'Academic Medical Center',
        'document_types': ['admission-notes', 'progress-notes', 'procedure-notes',
                          'discharge-summaries', 'teaching-cases', 'research-data', 'imaging-studies'],
        'count_per_type': 4  # 28 total
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
        
        'prescriptions': f"""Generate a realistic but synthetic prescription record for a {clinic_specialty} clinic.
Include: patient name (synthetic), medication name, dosage, frequency, duration, prescriber.
Use realistic medical terminology. All data must be synthetic. Keep it concise (150-300 words).""",
        
        'injury-reports': f"""Generate a realistic but synthetic injury report for an {clinic_specialty} clinic.
Include: mechanism of injury, physical examination, treatment provided, disposition.
Use realistic medical terminology. All data must be synthetic. Keep it concise (200-400 words).""",
        
        'diagnostic-notes': f"""Generate a realistic but synthetic diagnostic note for an {clinic_specialty} clinic.
Include: presenting symptoms, differential diagnosis, diagnostic reasoning, treatment plan.
All data must be synthetic. Keep it concise (200-400 words).""",
        
        'discharge-instructions': f"""Generate realistic but synthetic discharge instructions for an {clinic_specialty} clinic.
Include: diagnosis, treatment provided, home care instructions, follow-up recommendations, warning signs.
All data must be synthetic. Keep it concise (200-400 words).""",
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
    
    print("📝 Generating ~213 synthetic clinical documents...")
    print("   Using Claude Sonnet 4.5 (estimated cost: ~$1.67)")
    
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
