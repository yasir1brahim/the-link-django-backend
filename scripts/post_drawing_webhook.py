#!/usr/bin/env python3
"""
Helper script to POST drawing parser output to the webhook endpoint.

Workflow:
1. Upload a drawing file via the UI or API (creates DrawingFile + pending DrawingExtraction)
2. Run your parser locally on the PDF
3. Use this script to POST the parser output to the webhook

Usage:
    # List pending extractions to find the extraction_id
    python scripts/post_drawing_webhook.py --list

    # POST parser output from a JSON file
    python scripts/post_drawing_webhook.py --extraction-id=5 --file=parser_output.json

    # POST with inline JSON (for quick testing)
    python scripts/post_drawing_webhook.py --extraction-id=5 --status=PROCESSING

    # Full success flow with data
    python scripts/post_drawing_webhook.py --extraction-id=5 --file=parser_output.json --status=SUCCESS
"""
import argparse
import json
import uuid
import sys
import os

# Add the project root to the path so we can import Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'the_link.settings')

import django
django.setup()

import requests
from django.conf import settings
from apps.deliverables.models import (
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
)


def list_extractions(project_id=None, status=None):
    """List extractions with their IDs."""
    qs = DrawingExtraction.objects.select_related('drawing_file__project').order_by('-created_at')

    if project_id:
        qs = qs.filter(drawing_file__project_id=project_id)
    if status:
        qs = qs.filter(status=status)

    extractions = qs[:20]

    if not extractions:
        print("No extractions found.")
        return

    print(f"{'ID':<6} {'Status':<12} {'Project':<30} {'File':<40}")
    print("-" * 90)
    for ext in extractions:
        project_name = ext.drawing_file.project.name[:28] if ext.drawing_file.project else "N/A"
        file_name = ext.drawing_file.file_name[:38]
        print(f"{ext.id:<6} {ext.status:<12} {project_name:<30} {file_name:<40}")


def post_webhook(extraction_id, status, data=None, base_url="http://localhost:8000"):
    """POST to the webhook endpoint."""
    url = f"{base_url}/api/deliverables/webhooks/drawing-extraction/"

    payload = {
        "event_id": str(uuid.uuid4()),
        "extraction_id": extraction_id,
        "new_status": status,
    }

    if status == "PROCESSING":
        pass  # No additional fields needed

    elif status in ("SUCCESS", "PARTIAL_SUCCESS"):
        payload["model_version"] = data.get("model_version", "local-dev")
        payload["processing_time_ms"] = data.get("processing_time_ms", 0)
        payload["output_s3_key"] = data.get("output_s3_key", f"local/extraction_{extraction_id}.json")
        payload["data"] = {
            "total_pages": data.get("total_pages", len(data.get("pages", []))),
            "pages": data.get("pages", []),
        }
        if data.get("failure_summary"):
            payload["failure_summary"] = data["failure_summary"]

    elif status == "FAILED":
        payload["error_message"] = data.get("error_message", "Manual failure for testing")
        payload["failure_summary"] = data.get("failure_summary")

    print(f"\nPOSTing to {url}")
    print(f"Payload: {json.dumps(payload, indent=2)[:500]}...")

    response = requests.post(url, json=payload)

    print(f"\nResponse: {response.status_code}")
    if response.text:
        print(f"Body: {response.text}")

    return response.status_code == 200


def main():
    parser = argparse.ArgumentParser(description="POST drawing parser output to webhook")
    parser.add_argument("--list", action="store_true", help="List pending extractions")
    parser.add_argument("--project-id", type=int, help="Filter by project ID when listing")
    parser.add_argument("--extraction-id", type=int, help="Extraction ID to update")
    parser.add_argument("--status", choices=["PROCESSING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED"],
                        help="New status to set")
    parser.add_argument("--file", type=str, help="JSON file with parser output")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for the API")

    args = parser.parse_args()

    if args.list:
        list_extractions(project_id=args.project_id)
        return

    if not args.extraction_id:
        parser.error("--extraction-id is required (use --list to find IDs)")

    if not args.status:
        parser.error("--status is required")

    # Load data from file if provided
    data = {}
    if args.file:
        with open(args.file) as f:
            data = json.load(f)

    # For SUCCESS/PARTIAL_SUCCESS, we need pages data
    if args.status in ("SUCCESS", "PARTIAL_SUCCESS") and not data.get("pages"):
        print("Warning: No 'pages' in data. The webhook will create 0 notes.")
        print("Provide a JSON file with parser output using --file")

    success = post_webhook(
        extraction_id=args.extraction_id,
        status=args.status,
        data=data,
        base_url=args.base_url,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
