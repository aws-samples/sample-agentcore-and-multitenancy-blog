#!/usr/bin/env python3
# Copyright 2026 Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: MIT-0

"""
Seed HAPI FHIR server with synthetic patient data tagged by clinic.

Creates Patient and Observation resources on the public HAPI FHIR server
(https://hapi.fhir.org/baseR4) with clinic-scoped tags so the FHIR MCP
Lambda can demonstrate tenant isolation.

Each resource is tagged with:
  meta.tag = [{"system": "clinic", "code": "<clinic_id>"}]

This allows the FHIR MCP Lambda to filter by _tag=clinic|<clinic_id>.

Usage:
    python scripts/seed_fhir_data.py
    python scripts/seed_fhir_data.py --base-url http://localhost:8080/fhir
"""

import json
import sys
import time
import requests
import click

FHIR_BASE_URL = "https://hapi.fhir.org/baseR4"

# Synthetic patients mapped to clinics (matches existing project structure)
PATIENTS = [
    {
        "clinic_id": "clinic-a",
        "given": "John",
        "family": "Smith",
        "gender": "male",
        "birthDate": "1965-03-15",
    },
    {
        "clinic_id": "clinic-a",
        "given": "Maria",
        "family": "Garcia",
        "gender": "female",
        "birthDate": "1978-07-22",
    },
    {
        "clinic_id": "clinic-b",
        "given": "Robert",
        "family": "Johnson",
        "gender": "male",
        "birthDate": "1952-11-08",
    },
    {
        "clinic_id": "clinic-b",
        "given": "Sarah",
        "family": "Williams",
        "gender": "female",
        "birthDate": "1990-01-30",
    },
    {
        "clinic_id": "hospital-a",
        "given": "James",
        "family": "Anderson",
        "gender": "male",
        "birthDate": "1971-09-12",
    },
    {
        "clinic_id": "hospital-a",
        "given": "Emily",
        "family": "Chen",
        "gender": "female",
        "birthDate": "1985-04-18",
    },
    {
        "clinic_id": "clinic-e",
        "given": "Michael",
        "family": "Foster",
        "gender": "male",
        "birthDate": "1958-12-03",
    },
    {
        "clinic_id": "clinic-f",
        "given": "Linda",
        "family": "Martinez",
        "gender": "female",
        "birthDate": "1969-06-25",
    },
]

# Observations (lab results / vitals) to create for each patient
OBSERVATION_TEMPLATES = [
    {
        "code_system": "http://loinc.org",
        "code": "85354-9",
        "display": "Blood pressure panel",
        "value": 120,
        "unit": "mmHg",
        "unit_code": "mm[Hg]",
    },
    {
        "code_system": "http://loinc.org",
        "code": "2339-0",
        "display": "Glucose [Mass/volume] in Blood",
        "value": 95,
        "unit": "mg/dL",
        "unit_code": "mg/dL",
    },
    {
        "code_system": "http://loinc.org",
        "code": "2093-3",
        "display": "Cholesterol [Mass/volume] in Serum or Plasma",
        "value": 185,
        "unit": "mg/dL",
        "unit_code": "mg/dL",
    },
]


def create_patient(base_url: str, patient_data: dict) -> str:
    """Create a Patient resource and return its ID."""
    resource = {
        "resourceType": "Patient",
        "meta": {
            "tag": [{"system": "clinic", "code": patient_data["clinic_id"]}]
        },
        "name": [
            {
                "use": "official",
                "family": patient_data["family"],
                "given": [patient_data["given"]],
            }
        ],
        "gender": patient_data["gender"],
        "birthDate": patient_data["birthDate"],
    }

    resp = requests.post(
        f"{base_url}/Patient",
        json=resource,
        headers={"Content-Type": "application/fhir+json"},
        timeout=15,
    )
    resp.raise_for_status()
    created = resp.json()
    return created["id"]


def create_observation(base_url: str, patient_id: str, clinic_id: str, template: dict) -> str:
    """Create an Observation resource linked to a patient."""
    resource = {
        "resourceType": "Observation",
        "meta": {
            "tag": [{"system": "clinic", "code": clinic_id}]
        },
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                        "display": "Laboratory",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": template["code_system"],
                    "code": template["code"],
                    "display": template["display"],
                }
            ],
            "text": template["display"],
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": "2026-01-15T10:30:00Z",
        "valueQuantity": {
            "value": template["value"],
            "unit": template["unit"],
            "system": "http://unitsofmeasure.org",
            "code": template["unit_code"],
        },
    }

    resp = requests.post(
        f"{base_url}/Observation",
        json=resource,
        headers={"Content-Type": "application/fhir+json"},
        timeout=15,
    )
    resp.raise_for_status()
    created = resp.json()
    return created["id"]


@click.command()
@click.option("--base-url", default=FHIR_BASE_URL, help="FHIR server base URL")
@click.option("--dry-run", is_flag=True, help="Print resources without creating them")
def seed(base_url, dry_run):
    """Seed HAPI FHIR server with clinic-scoped synthetic data."""
    click.echo(f"🏥 Seeding FHIR data to: {base_url}")
    click.echo(f"   Patients: {len(PATIENTS)}")
    click.echo(f"   Observations per patient: {len(OBSERVATION_TEMPLATES)}")
    click.echo("")

    if dry_run:
        click.echo("🔍 DRY RUN — no resources will be created")
        for p in PATIENTS:
            click.echo(f"   Would create: {p['given']} {p['family']} (clinic: {p['clinic_id']})")
        return

    created_patients = []
    created_observations = 0

    for patient_data in PATIENTS:
        try:
            patient_id = create_patient(base_url, patient_data)
            created_patients.append({
                "id": patient_id,
                "name": f"{patient_data['given']} {patient_data['family']}",
                "clinic_id": patient_data["clinic_id"],
            })
            click.echo(
                f"  ✅ Patient: {patient_data['given']} {patient_data['family']} "
                f"(ID: {patient_id}, clinic: {patient_data['clinic_id']})"
            )

            # Create observations for this patient
            for template in OBSERVATION_TEMPLATES:
                obs_id = create_observation(base_url, patient_id, patient_data["clinic_id"], template)
                created_observations += 1
                click.echo(f"     📊 Observation: {template['display']} (ID: {obs_id})")

            # Be nice to the public server
            time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            click.echo(f"  ❌ Failed to create {patient_data['given']} {patient_data['family']}: {e}")
            continue

    click.echo("")
    click.echo(f"🎉 Seeding complete!")
    click.echo(f"   Created {len(created_patients)} patients, {created_observations} observations")
    click.echo("")

    # Output a mapping file for reference
    mapping_file = "credentials/fhir_patient_mapping.json"
    try:
        with open(mapping_file, "w") as f:
            json.dump(created_patients, f, indent=2)
        click.echo(f"📄 Patient ID mapping saved to: {mapping_file}")
    except Exception as e:
        click.echo(f"⚠️  Could not save mapping file: {e}")

    # Print summary by clinic
    click.echo("")
    click.echo("📋 Summary by clinic:")
    clinics = {}
    for p in created_patients:
        clinics.setdefault(p["clinic_id"], []).append(p)
    for clinic_id, patients in sorted(clinics.items()):
        click.echo(f"   {clinic_id}: {', '.join(p['name'] for p in patients)}")


if __name__ == "__main__":
    seed()
