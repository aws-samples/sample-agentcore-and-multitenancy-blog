# Healthcare Clinic Profiles

## Overview

This document defines the 8 clinic profiles for the healthcare multi-tenant demo, including their specialties, user personas, document types, and expected usage patterns. These profiles demonstrate complete tenant isolation and tier differentiation.

---

## Basic Tier Clinics (4 Clinics)

### Clinic A: Family Practice Medical Center

**Clinic ID**: `clinic-a`  
**Specialty**: Family Medicine / Primary Care  
**Service Tier**: Basic  
**Location**: Suburban community  
**Patient Volume**: ~50 patients/day  

#### User Personas
- **Dr. Sarah Smith** (`dr.smith@clinic-a.com`)
  - Role: Primary Care Physician
  - Use Cases: Review patient intake forms, check lab results, write appointment notes
  - Typical Queries: "Show me recent patient intake forms", "What are today's lab results?"

- **Nurse Jennifer Lee** (`nurse.lee@clinic-a.com`)
  - Role: Registered Nurse
  - Use Cases: Document vital signs, review prescriptions, patient triage
  - Typical Queries: "List patients with abnormal vital signs", "Show pending prescriptions"

- **Admin Maria Garcia** (`admin.garcia@clinic-a.com`)
  - Role: Medical Office Administrator
  - Use Cases: Schedule management, document organization
  - Typical Queries: "Find all intake forms from last week", "List incomplete patient records"

#### Document Types (20-30 documents)
- **Patient Intake Forms**: New patient registration, medical history
- **Appointment Notes**: Visit summaries, chief complaints, treatment plans
- **Lab Results**: Basic panels (CBC, metabolic panel, urinalysis)
- **Prescriptions**: Medication orders, refill requests
- **Vital Signs Logs**: Blood pressure, temperature, weight tracking

#### Expected Usage Patterns
- Peak hours: 8am-12pm, 2pm-5pm
- Average queries: 3-5 per day
- Document searches: Recent documents (last 7-30 days)
- Rate limit tolerance: 0.5 req/sec sufficient for single-user workflows

#### S3 Document Prefix
```
s3://healthcare-documents/basic-tier/clinic-a/
├── patient-intake/
├── appointment-notes/
├── lab-results/
└── prescriptions/
```

---

### Clinic B: QuickCare Urgent Care

**Clinic ID**: `clinic-b`  
**Specialty**: Urgent Care / Walk-in Clinic  
**Service Tier**: Basic  
**Location**: Urban shopping district  
**Patient Volume**: ~80 patients/day (high turnover)  

#### User Personas
- **Dr. Michael Chen** (`dr.chen@clinic-b.com`)
  - Role: Urgent Care Physician
  - Use Cases: Quick patient assessments, injury documentation, rapid diagnosis
  - Typical Queries: "Show me recent injury reports", "List patients with fever symptoms"

- **PA Jessica Martinez** (`pa.martinez@clinic-b.com`)
  - Role: Physician Assistant
  - Use Cases: Minor procedures, wound care documentation, follow-up instructions
  - Typical Queries: "Find all laceration cases this week", "Show pending X-ray results"

#### Document Types (25-35 documents)
- **Patient Intake Forms**: Rapid triage forms, chief complaint documentation
- **Injury Reports**: Laceration, sprain, fracture documentation
- **Diagnostic Notes**: Quick assessment notes, treatment decisions
- **Lab Results**: Rapid tests (strep, flu, COVID-19)
- **Discharge Instructions**: Post-visit care instructions, follow-up recommendations

#### Expected Usage Patterns
- Peak hours: 10am-2pm, 5pm-9pm (after-work rush)
- Average queries: 5-8 per day (higher volume, quick searches)
- Document searches: Same-day documents, symptom-based searches
- Rate limit challenge: May occasionally hit 0.5 req/sec limit during busy periods

#### S3 Document Prefix
```
s3://healthcare-documents/basic-tier/clinic-b/
├── patient-intake/
├── injury-reports/
├── diagnostic-notes/
└── discharge-instructions/
```

---

### Clinic C: Bright Beginnings Pediatrics

**Clinic ID**: `clinic-c`  
**Specialty**: Pediatrics  
**Service Tier**: Basic  
**Location**: Family-oriented suburb  
**Patient Volume**: ~40 patients/day  

#### User Personas
- **Dr. Emily Rodriguez** (`dr.rodriguez@clinic-c.com`)
  - Role: Pediatrician
  - Use Cases: Well-child visits, vaccination records, growth tracking
  - Typical Queries: "Show vaccination schedules for patients due this month", "List growth charts for 2-year-olds"

- **Nurse Practitioner David Kim** (`np.kim@clinic-c.com`)
  - Role: Pediatric Nurse Practitioner
  - Use Cases: Sick visits, developmental assessments, parent education
  - Typical Queries: "Find all ear infection cases this season", "Show developmental milestone assessments"

#### Document Types (20-30 documents)
- **Well-Child Visit Notes**: Growth measurements, developmental milestones
- **Vaccination Records**: Immunization schedules, vaccine administration logs
- **Sick Visit Notes**: Common pediatric illnesses (ear infections, colds, rashes)
- **Growth Charts**: Height, weight, head circumference tracking
- **Parent Education Materials**: Feeding guidelines, safety instructions

#### Expected Usage Patterns
- Peak hours: 9am-11am (morning appointments), 3pm-5pm (after-school)
- Average queries: 3-4 per day
- Document searches: Age-based searches, vaccination status checks
- Rate limit tolerance: 0.5 req/sec adequate for scheduled appointment workflow

#### S3 Document Prefix
```
s3://healthcare-documents/basic-tier/clinic-c/
├── well-child-visits/
├── vaccination-records/
├── sick-visit-notes/
└── growth-charts/
```

---

### Clinic D: Wellness Internal Medicine

**Clinic ID**: `clinic-d`  
**Specialty**: Internal Medicine  
**Service Tier**: Basic  
**Location**: Medical office building  
**Patient Volume**: ~35 patients/day  

#### User Personas
- **Dr. Robert Johnson** (`dr.johnson@clinic-d.com`)
  - Role: Internist
  - Use Cases: Chronic disease management, preventive care, complex medical histories
  - Typical Queries: "Show all diabetes patients with recent A1C results", "List hypertension medication changes"

- **Nurse Coordinator Lisa Brown** (`nurse.brown@clinic-d.com`)
  - Role: Care Coordinator
  - Use Cases: Patient follow-up, medication reconciliation, care plan coordination
  - Typical Queries: "Find patients due for annual physicals", "Show pending specialist referrals"

#### Document Types (25-30 documents)
- **Chronic Disease Management Notes**: Diabetes, hypertension, COPD management
- **Annual Physical Exams**: Comprehensive health assessments, preventive screenings
- **Lab Results**: Lipid panels, A1C, thyroid function tests
- **Medication Lists**: Current medications, medication reconciliation notes
- **Specialist Referrals**: Cardiology, endocrinology, pulmonology referrals

#### Expected Usage Patterns
- Peak hours: 8am-12pm (morning appointments)
- Average queries: 4-6 per day
- Document searches: Longitudinal patient data, chronic condition tracking
- Rate limit tolerance: 0.5 req/sec sufficient for thorough patient review workflow

#### S3 Document Prefix
```
s3://healthcare-documents/basic-tier/clinic-d/
├── chronic-disease-notes/
├── annual-physicals/
├── lab-results/
└── specialist-referrals/
```

---

## Premium Tier Clinics (4 Clinics)

### Hospital A: Metropolitan Multi-Specialty Medical Center

**Clinic ID**: `hospital-a`  
**Specialty**: Multi-Specialty Hospital (Cardiology, Oncology, Surgery)  
**Service Tier**: Premium  
**Location**: Urban academic medical center  
**Patient Volume**: ~200 patients/day across departments  

#### User Personas
- **Dr. Amanda Foster** (`dr.foster@hospital-a.com`)
  - Role: Cardiologist
  - Use Cases: Complex diagnostic interpretation, multi-document correlation, research queries
  - Typical Queries: "Analyze cardiac catheterization trends across all patients", "Compare echocardiogram results with stress test findings"

- **Dr. James Wilson** (`dr.wilson@hospital-a.com`)
  - Role: Surgical Oncologist
  - Use Cases: Pre-operative planning, pathology review, outcome tracking
  - Typical Queries: "Show all pathology reports with positive margins", "Correlate imaging findings with surgical outcomes"

- **Research Coordinator Dr. Lisa Chen** (`dr.chen@hospital-a.com`)
  - Role: Clinical Research Coordinator
  - Use Cases: Population health analytics, outcome studies, quality metrics
  - Typical Queries: "Identify trends in post-operative complications", "Generate summary of cancer staging distribution"

#### Document Types (20-30 documents)
- **Diagnostic Reports**: Cardiac catheterization, stress tests, echocardiograms
- **Imaging Studies**: CT scans, MRI reports, PET scans
- **Pathology Reports**: Surgical pathology, cytology, immunohistochemistry
- **Surgical Notes**: Operative reports, post-operative notes, discharge summaries
- **Specialist Consultations**: Multi-disciplinary team notes, tumor board discussions
- **Research Data**: Clinical trial documentation, outcome tracking

#### Expected Usage Patterns
- Peak hours: 7am-6pm (extended clinical hours)
- Average queries: 15-20 per day (multiple departments)
- Document searches: Complex multi-document analysis, longitudinal studies
- Rate limit requirement: 2 req/sec needed for advanced analytics workflows
- Premium features: Web search for latest clinical guidelines, multi-document correlation

#### S3 Document Prefix
```
s3://healthcare-documents/premium-tier/hospital-a/
├── diagnostic-reports/
├── imaging-studies/
├── pathology-reports/
├── surgical-notes/
├── specialist-consultations/
└── research-data/
```

---

### Clinic E: Advanced Cardiology Associates

**Clinic ID**: `clinic-e`  
**Specialty**: Cardiology  
**Service Tier**: Premium  
**Location**: Specialty medical campus  
**Patient Volume**: ~60 patients/day  

#### User Personas
- **Dr. Thomas Anderson** (`dr.anderson@clinic-e.com`)
  - Role: Interventional Cardiologist
  - Use Cases: Pre-procedure planning, post-procedure follow-up, risk stratification
  - Typical Queries: "Show all patients with ejection fraction <40%", "Analyze stent outcomes over 6 months"

- **Cardiologist Dr. Priya Patel** (`dr.patel@clinic-e.com`)
  - Role: Non-invasive Cardiologist
  - Use Cases: Diagnostic test interpretation, medication optimization, heart failure management
  - Typical Queries: "Compare echocardiogram results with cardiac MRI findings", "Search latest guidelines for heart failure management"

#### Document Types (20-30 documents)
- **Cardiac Catheterization Reports**: Angiography, PCI procedures, stent placements
- **Echocardiogram Reports**: Transthoracic, transesophageal, stress echo
- **Stress Test Results**: Exercise stress tests, nuclear stress tests
- **Holter Monitor Reports**: 24-48 hour cardiac monitoring
- **Cardiac MRI/CT Reports**: Advanced cardiac imaging
- **Heart Failure Management Notes**: Medication titration, device therapy

#### Expected Usage Patterns
- Peak hours: 7am-5pm (procedure days and clinic days)
- Average queries: 10-12 per day
- Document searches: Multi-modality imaging correlation, guideline-based searches
- Rate limit requirement: 2 req/sec for rapid multi-document review
- Premium features: Web search for latest ACC/AHA guidelines, advanced analytics

#### S3 Document Prefix
```
s3://healthcare-documents/premium-tier/clinic-e/
├── catheterization-reports/
├── echocardiogram-reports/
├── stress-test-results/
├── holter-monitor-reports/
└── cardiac-imaging/
```

---

### Clinic F: Comprehensive Cancer Care Center

**Clinic ID**: `clinic-f`  
**Specialty**: Oncology  
**Service Tier**: Premium  
**Location**: Cancer treatment center  
**Patient Volume**: ~50 patients/day  

#### User Personas
- **Dr. Rachel Green** (`dr.green@clinic-f.com`)
  - Role: Medical Oncologist
  - Use Cases: Treatment planning, chemotherapy protocols, clinical trial matching
  - Typical Queries: "Show all breast cancer patients with HER2+ status", "Search latest immunotherapy trials for lung cancer"

- **Dr. Mark Davis** (`dr.davis@clinic-f.com`)
  - Role: Radiation Oncologist
  - Use Cases: Radiation planning, dose calculations, treatment response tracking
  - Typical Queries: "Analyze radiation treatment outcomes by tumor type", "Correlate imaging response with pathology findings"

#### Document Types (20-30 documents)
- **Pathology Reports**: Tumor histology, molecular markers, genetic testing
- **Imaging Studies**: CT, MRI, PET scans for staging and response assessment
- **Treatment Plans**: Chemotherapy protocols, radiation plans, immunotherapy regimens
- **Clinical Trial Documents**: Eligibility assessments, trial enrollment forms
- **Multidisciplinary Team Notes**: Tumor board discussions, treatment recommendations
- **Genomic Testing Reports**: Next-generation sequencing, biomarker analysis

#### Expected Usage Patterns
- Peak hours: 8am-5pm (clinic and treatment planning)
- Average queries: 12-15 per day
- Document searches: Biomarker-based searches, treatment outcome analysis
- Rate limit requirement: 2 req/sec for complex treatment planning workflows
- Premium features: Web search for latest NCCN guidelines, clinical trial databases

#### S3 Document Prefix
```
s3://healthcare-documents/premium-tier/clinic-f/
├── pathology-reports/
├── imaging-studies/
├── treatment-plans/
├── clinical-trial-docs/
├── tumor-board-notes/
└── genomic-testing/
```

---

### Hospital B: University Academic Medical Center

**Clinic ID**: `hospital-b`  
**Specialty**: Academic Medical Center (Teaching Hospital)  
**Service Tier**: Premium  
**Location**: University campus  
**Patient Volume**: ~250 patients/day (includes residents and fellows)  

#### User Personas
- **Dr. Elizabeth Martinez** (`dr.martinez@hospital-b.com`)
  - Role: Department Chair / Attending Physician
  - Use Cases: Complex case review, teaching rounds, quality improvement
  - Typical Queries: "Generate summary of all ICU admissions this month", "Analyze readmission rates by diagnosis"

- **Dr. Kevin Nguyen** (`dr.nguyen@hospital-b.com`)
  - Role: Chief Resident
  - Use Cases: Patient handoffs, case presentations, literature review
  - Typical Queries: "Show all patients admitted with sepsis", "Search latest evidence for antibiotic stewardship"

- **Research Fellow Dr. Sarah Thompson** (`dr.thompson@hospital-b.com`)
  - Role: Clinical Research Fellow
  - Use Cases: Data extraction for research, outcome studies, publication preparation
  - Typical Queries: "Extract structured data from all surgical complications", "Identify patients meeting inclusion criteria for study"

#### Document Types (20-30 documents)
- **Admission Notes**: H&P, admission orders, initial assessments
- **Progress Notes**: Daily progress notes, consultant notes
- **Procedure Notes**: Surgical procedures, interventional procedures
- **Discharge Summaries**: Hospital course, discharge medications, follow-up plans
- **Teaching Case Presentations**: Grand rounds, morbidity & mortality conferences
- **Research Data**: Clinical trial data, quality improvement projects
- **Imaging Studies**: Comprehensive radiology reports across all modalities
- **Pathology Reports**: Surgical pathology, autopsy reports

#### Expected Usage Patterns
- Peak hours: 6am-8pm (extended academic hours, teaching rounds)
- Average queries: 20-25 per day (multiple users, teaching activities)
- Document searches: Complex queries, data extraction, population analytics
- Rate limit requirement: 2 req/sec essential for high-volume academic workflows
- Premium features: Web search for latest research, advanced multi-document analytics

#### S3 Document Prefix
```
s3://healthcare-documents/premium-tier/hospital-b/
├── admission-notes/
├── progress-notes/
├── procedure-notes/
├── discharge-summaries/
├── teaching-cases/
├── research-data/
├── imaging-studies/
└── pathology-reports/
```

---

## Cognito User Creation Plan

### Phase 1.2 Implementation (Days 4-6)

#### User Pool Configuration
```bash
# Add custom attributes to existing user pool
aws cognito-idp add-custom-attributes \
  --user-pool-id us-east-1_JlX0bKAgU \
  --custom-attributes \
    Name=clinic_id,AttributeDataType=String,Required=true \
    Name=role,AttributeDataType=String,Required=false
```

#### Test User Creation Script
```python
# scripts/create_test_users.py
import boto3

cognito = boto3.client('cognito-idp')
USER_POOL_ID = 'us-east-1_JlX0bKAgU'

# Basic Tier Users
basic_users = [
    {'username': 'dr.smith@clinic-a.com', 'clinic_id': 'clinic-a', 'tier': 'basic', 'role': 'physician'},
    {'username': 'nurse.lee@clinic-a.com', 'clinic_id': 'clinic-a', 'tier': 'basic', 'role': 'nurse'},
    {'username': 'dr.chen@clinic-b.com', 'clinic_id': 'clinic-b', 'tier': 'basic', 'role': 'physician'},
    {'username': 'dr.rodriguez@clinic-c.com', 'clinic_id': 'clinic-c', 'tier': 'basic', 'role': 'physician'},
    {'username': 'dr.johnson@clinic-d.com', 'clinic_id': 'clinic-d', 'tier': 'basic', 'role': 'physician'},
]

# Premium Tier Users
premium_users = [
    {'username': 'dr.foster@hospital-a.com', 'clinic_id': 'hospital-a', 'tier': 'premium', 'role': 'physician'},
    {'username': 'dr.wilson@hospital-a.com', 'clinic_id': 'hospital-a', 'tier': 'premium', 'role': 'physician'},
    {'username': 'dr.anderson@clinic-e.com', 'clinic_id': 'clinic-e', 'tier': 'premium', 'role': 'physician'},
    {'username': 'dr.green@clinic-f.com', 'clinic_id': 'clinic-f', 'tier': 'premium', 'role': 'physician'},
    {'username': 'dr.martinez@hospital-b.com', 'clinic_id': 'hospital-b', 'tier': 'premium', 'role': 'physician'},
]

# Create users with custom attributes
for user in basic_users + premium_users:
    cognito.admin_create_user(
        UserPoolId=USER_POOL_ID,
        Username=user['username'],
        UserAttributes=[
            {'Name': 'email', 'Value': user['username']},
            {'Name': 'custom:tenant_id', 'Value': user['tier']},
            {'Name': 'custom:clinic_id', 'Value': user['clinic_id']},
            {'Name': 'custom:role', 'Value': user['role']},
        ],
        TemporaryPassword='TempPass123!',
        MessageAction='SUPPRESS'  # Don't send email for demo users
    )
```

---

## Demo Scenario Mapping

### Scenario 1: Basic Tier - Document Search & Isolation
- **User**: Dr. Smith @ Clinic A
- **Query**: "Show me recent patient intake forms"
- **Demonstrates**: S3 prefix isolation, basic document search, Nova Micro performance

### Scenario 2: Basic Tier - Rate Limiting
- **User**: Dr. Chen @ Clinic B (Urgent Care)
- **Query**: Multiple rapid queries during busy period
- **Demonstrates**: 0.5 req/sec throttling, burst limit enforcement

### Scenario 3: Premium Tier - Advanced Analytics
- **User**: Dr. Foster @ Hospital A
- **Query**: "Analyze cardiac catheterization trends across all patients"
- **Demonstrates**: Multi-document correlation, Claude Sonnet 4.5 quality, 2 req/sec rate

### Scenario 4: Premium Tier - Web Search
- **User**: Dr. Patel @ Clinic E
- **Query**: "Search latest ACC/AHA guidelines for heart failure management"
- **Demonstrates**: Premium-only web search capability, external data integration

### Scenario 5: Cross-Clinic Isolation
- **User**: Dr. Smith @ Clinic A attempts to access Clinic B documents
- **Demonstrates**: Complete tenant isolation via S3 prefix enforcement

---

## Summary Statistics

| Metric | Basic Tier | Premium Tier |
|--------|------------|--------------|
| **Total Clinics** | 4 | 4 |
| **Total Users** | 8-12 | 10-15 |
| **Documents per Clinic** | 20-35 | 50-100 |
| **Total Documents** | ~100-120 | ~280-360 |
| **Specialties** | Primary Care, Urgent Care, Pediatrics, Internal Medicine | Multi-Specialty Hospital, Cardiology, Oncology, Academic Medical Center |
| **Rate Limit** | 0.5 req/sec | 2 req/sec |
| **Daily Quota** | 5 requests | 20 requests |
| **Model** | Nova Micro | Claude Sonnet 4.5 |
| **Exclusive Features** | None | Web Search, Advanced Analytics, Multi-Document Correlation |

---

## Next Steps

1. **Phase 0 (Current)**: Review and approve clinic profiles
2. **Phase 1.2 (Days 4-6)**: Create Cognito users with custom attributes
3. **Phase 2.1 (Week 1)**: Generate synthetic clinical documents per clinic profile
4. **Phase 4.2 (Week 2)**: Implement demo scenarios using these profiles
