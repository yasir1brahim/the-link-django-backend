"""
Management command to seed test drawing data for frontend development.

Usage:
    # Seed data directly into database for a project
    docker-compose exec web python manage.py seed_drawing_data --project-id=1

    # Seed via webhook simulation (tests the full webhook flow)
    docker-compose exec web python manage.py seed_drawing_data --project-id=1 --via-webhook

    # Use a specific project version
    docker-compose exec web python manage.py seed_drawing_data --project-id=1 --version-id=2

    # Clear existing drawing data first
    docker-compose exec web python manage.py seed_drawing_data --project-id=1 --clear

    # Seed multiple files
    docker-compose exec web python manage.py seed_drawing_data --project-id=1 --file-count=3
"""
import uuid
import json
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory
from django.db import transaction

from apps.deliverables.models import (
    Project,
    ProjectVersion,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingPage,
    DrawingPageType,
    DrawingPageExtractionStatus,
    DrawingNoteSection,
    DrawingNote,
)
from apps.deliverables.views.drawing_views import drawing_extraction_webhook


# Sample drawing data that mimics real mechanical/electrical drawing notes
SAMPLE_DRAWING_FILES = [
    {
        "file_name": "M-001 Mechanical General Notes.pdf",
        "total_pages": 3,
        "pages": [
            {
                "page_number": 1,
                "page_type": "DRAWING",
                "extraction_status": "SUCCESS",
                "note_sections": [
                    {
                        "header": "GENERAL MECHANICAL NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "GENERAL", "text": "All work shall comply with the latest edition of the International Mechanical Code (IMC) and all applicable local codes and ordinances."},
                            {"note_number": 2, "category": "GENERAL", "text": "Contractor shall verify all dimensions and conditions at the job site prior to fabrication and installation of any equipment."},
                            {"note_number": 3, "category": "GENERAL", "text": "All mechanical equipment shall be installed in accordance with manufacturer's recommendations and approved shop drawings."},
                            {"note_number": 4, "category": "SUBMITTALS", "text": "Submit shop drawings, product data, and samples for all mechanical equipment within 30 days of contract award."},
                            {"note_number": 5, "category": "SUBMITTALS", "text": "Include performance curves, electrical characteristics, and sound ratings with all equipment submittals."},
                        ]
                    },
                    {
                        "header": "HVAC NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "HVAC", "text": "All ductwork shall be fabricated and installed in accordance with SMACNA standards."},
                            {"note_number": 2, "category": "HVAC", "text": "Provide access doors at all fire dampers, volume dampers, and coils for inspection and maintenance."},
                            {"note_number": 3, "category": "HVAC", "text": "Seal all duct penetrations through fire-rated walls with UL-listed fire stopping material."},
                        ]
                    }
                ]
            },
            {
                "page_number": 2,
                "page_type": "DRAWING",
                "extraction_status": "SUCCESS",
                "note_sections": [
                    {
                        "header": "PIPING NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "PIPING", "text": "All piping shall be installed with proper slope for drainage. Minimum slope shall be 1/4\" per foot unless noted otherwise."},
                            {"note_number": 2, "category": "PIPING", "text": "Provide isolation valves at all equipment connections and at branch takeoffs from mains."},
                            {"note_number": 3, "category": "PIPING", "text": "Insulate all hot water piping with 1\" thick fiberglass insulation with vapor barrier jacket."},
                            {"note_number": 4, "category": "PIPING", "text": "Test all piping systems at 1.5 times the working pressure for a minimum of 2 hours."},
                        ]
                    }
                ]
            },
            {
                "page_number": 3,
                "page_type": "SCHEDULE",
                "extraction_status": "SUCCESS",
                "note_sections": []
            }
        ]
    },
    {
        "file_name": "E-001 Electrical General Notes.pdf",
        "total_pages": 2,
        "pages": [
            {
                "page_number": 1,
                "page_type": "DRAWING",
                "extraction_status": "SUCCESS",
                "note_sections": [
                    {
                        "header": "GENERAL ELECTRICAL NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "GENERAL", "text": "All electrical work shall comply with the National Electrical Code (NEC) and all applicable local codes."},
                            {"note_number": 2, "category": "GENERAL", "text": "Contractor shall verify all existing conditions and coordinate with other trades before installation."},
                            {"note_number": 3, "category": "GENERAL", "text": "Provide ground fault circuit interrupter (GFCI) protection for all receptacles within 6 feet of water sources."},
                            {"note_number": 4, "category": "WIRING", "text": "All branch circuit wiring shall be minimum #12 AWG copper unless noted otherwise on drawings."},
                            {"note_number": 5, "category": "WIRING", "text": "Use MC cable or EMT conduit for all exposed wiring locations."},
                        ]
                    },
                    {
                        "header": "LIGHTING NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "LIGHTING", "text": "All LED fixtures shall have minimum efficacy of 100 lumens per watt and CRI of 80 or greater."},
                            {"note_number": 2, "category": "LIGHTING", "text": "Provide 0-10V dimming capability for all fixtures in conference rooms and private offices."},
                            {"note_number": 3, "category": "LIGHTING", "text": "Emergency lighting shall provide minimum 1 foot-candle along paths of egress for 90 minutes."},
                        ]
                    }
                ]
            },
            {
                "page_number": 2,
                "page_type": "DRAWING",
                "extraction_status": "SUCCESS",
                "note_sections": [
                    {
                        "header": "FIRE ALARM NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "FIRE ALARM", "text": "Fire alarm system shall be addressable type with graphic annunciator panel at main entrance."},
                            {"note_number": 2, "category": "FIRE ALARM", "text": "Provide smoke detectors in all return air plenums and at each elevator lobby."},
                            {"note_number": 3, "category": "FIRE ALARM", "text": "Horn/strobe devices shall be installed per ADA requirements with 15 candela minimum in corridors."},
                        ]
                    }
                ]
            }
        ]
    },
    {
        "file_name": "P-001 Plumbing Notes.pdf",
        "total_pages": 2,
        "pages": [
            {
                "page_number": 1,
                "page_type": "DRAWING",
                "extraction_status": "SUCCESS",
                "note_sections": [
                    {
                        "header": "GENERAL PLUMBING NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "GENERAL", "text": "All plumbing work shall comply with the International Plumbing Code (IPC) and local amendments."},
                            {"note_number": 2, "category": "GENERAL", "text": "Provide cleanouts at base of all stacks, at changes of direction greater than 45 degrees, and at 50' intervals."},
                            {"note_number": 3, "category": "FIXTURES", "text": "All water closets shall be 1.28 GPF high-efficiency type with elongated bowl."},
                            {"note_number": 4, "category": "FIXTURES", "text": "Lavatory faucets shall be 0.5 GPM sensor-operated type with integral mixing valve."},
                        ]
                    },
                    {
                        "header": "WATER HEATER NOTES:",
                        "notes": [
                            {"note_number": 1, "category": "WATER HEATER", "text": "Electric water heaters shall have minimum thermal efficiency of 95% and be ENERGY STAR rated."},
                            {"note_number": 2, "category": "WATER HEATER", "text": "Provide thermostatic mixing valve at water heater outlet set to deliver 120°F at fixtures."},
                        ]
                    }
                ]
            },
            {
                "page_number": 2,
                "page_type": "DRAWING",
                "extraction_status": "FAILED",
                "note_sections": []
            }
        ]
    }
]


class Command(BaseCommand):
    help = 'Seed test drawing data for frontend development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-id',
            type=int,
            required=True,
            help='Project ID to seed drawing data for'
        )
        parser.add_argument(
            '--version-id',
            type=int,
            help='Project version ID (defaults to latest version)'
        )
        parser.add_argument(
            '--via-webhook',
            action='store_true',
            help='Seed data by simulating webhook calls instead of direct DB inserts'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing drawing data for this project before seeding'
        )
        parser.add_argument(
            '--file-count',
            type=int,
            default=2,
            help='Number of sample files to create (1-3, default: 2)'
        )

    def handle(self, *args, **options):
        project_id = options['project_id']
        version_id = options['version_id']
        via_webhook = options['via_webhook']
        clear = options['clear']
        file_count = min(max(options['file_count'], 1), 3)  # Clamp to 1-3

        # Validate project exists
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise CommandError(f'Project with ID {project_id} does not exist')

        # Get project version
        if version_id:
            try:
                project_version = ProjectVersion.objects.get(
                    id=version_id,
                    project=project
                )
            except ProjectVersion.DoesNotExist:
                raise CommandError(
                    f'Project version {version_id} does not exist for project {project_id}'
                )
        else:
            project_version = project.versions.order_by('-version_number').first()
            if not project_version:
                raise CommandError(f'Project {project_id} has no versions')

        self.stdout.write(
            f'Seeding drawing data for project "{project.name}" '
            f'(version {project_version.version_number})'
        )

        # Clear existing data if requested
        if clear:
            self._clear_drawing_data(project, project_version)

        # Seed the data
        sample_files = SAMPLE_DRAWING_FILES[:file_count]

        if via_webhook:
            self._seed_via_webhook(project, project_version, sample_files)
        else:
            self._seed_direct(project, project_version, sample_files)

        # Print summary
        notes_count = DrawingNote.objects.filter(
            section__page__drawing_file__project=project,
            section__page__drawing_file__project_version=project_version
        ).count()

        files_count = DrawingFile.objects.filter(
            project=project,
            project_version=project_version
        ).count()

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully seeded {files_count} drawing files with {notes_count} notes'
        ))
        self.stdout.write(
            f'\nTest the API with:\n'
            f'  curl http://localhost:8000/api/deliverables/projects/{project_id}/drawing-notes/'
        )

    def _clear_drawing_data(self, project, project_version):
        """Clear existing drawing data for the project/version."""
        deleted = DrawingFile.objects.filter(
            project=project,
            project_version=project_version
        ).delete()
        self.stdout.write(
            f'Cleared existing drawing data: {deleted}'
        )

    def _seed_direct(self, project, project_version, sample_files):
        """Seed data directly into the database."""
        self.stdout.write('Seeding data directly into database...')

        with transaction.atomic():
            for file_data in sample_files:
                # Create DrawingFile
                drawing_file = DrawingFile.objects.create(
                    project=project,
                    project_version=project_version,
                    file_name=file_data['file_name'],
                    file_s3_key=f'drawings/test/{uuid.uuid4()}.pdf',
                    md5=uuid.uuid4().hex,
                    total_pages=file_data['total_pages'],
                )
                self.stdout.write(f'  Created file: {file_data["file_name"]}')

                # Create DrawingExtraction
                extraction = DrawingExtraction.objects.create(
                    drawing_file=drawing_file,
                    status=DrawingExtractionStatus.SUCCESS,
                    model_version='test-v1.0',
                )

                # Create pages, sections, and notes
                for page_data in file_data['pages']:
                    page = DrawingPage.objects.create(
                        drawing_file=drawing_file,
                        extraction=extraction,
                        page_number=page_data['page_number'],
                        page_type=page_data['page_type'],
                        extraction_status=page_data['extraction_status'],
                    )

                    for section_data in page_data.get('note_sections', []):
                        section = DrawingNoteSection.objects.create(
                            page=page,
                            header=section_data['header'],
                        )

                        for note_data in section_data.get('notes', []):
                            DrawingNote.objects.create(
                                section=section,
                                note_number=note_data['note_number'],
                                category=note_data['category'],
                                text=note_data['text'],
                            )

    def _seed_via_webhook(self, project, project_version, sample_files):
        """Seed data by simulating webhook calls."""
        self.stdout.write('Seeding data via webhook simulation...')

        factory = RequestFactory()

        for file_data in sample_files:
            # First create the DrawingFile and pending extraction
            drawing_file = DrawingFile.objects.create(
                project=project,
                project_version=project_version,
                file_name=file_data['file_name'],
                file_s3_key=f'drawings/test/{uuid.uuid4()}.pdf',
                md5=uuid.uuid4().hex,
            )

            extraction = DrawingExtraction.objects.create(
                drawing_file=drawing_file,
                status=DrawingExtractionStatus.PENDING,
            )

            self.stdout.write(f'  Created file: {file_data["file_name"]} (extraction ID: {extraction.id})')

            # Simulate PROCESSING webhook
            processing_payload = {
                'event_id': str(uuid.uuid4()),
                'extraction_id': extraction.id,
                'new_status': 'PROCESSING',
            }
            request = factory.post(
                '/api/deliverables/webhooks/drawing-extraction/',
                data=json.dumps(processing_payload),
                content_type='application/json'
            )
            response = drawing_extraction_webhook(request)
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(
                    f'    PROCESSING webhook failed: {response.status_code}'
                ))
                continue

            # Simulate SUCCESS webhook with full data
            success_payload = {
                'event_id': str(uuid.uuid4()),
                'extraction_id': extraction.id,
                'new_status': 'SUCCESS',
                'model_version': 'test-v1.0',
                'processing_time_ms': 1234,
                'output_s3_key': f'outputs/{uuid.uuid4()}.json',
                'data': {
                    'total_pages': file_data['total_pages'],
                    'pages': file_data['pages'],
                }
            }
            request = factory.post(
                '/api/deliverables/webhooks/drawing-extraction/',
                data=json.dumps(success_payload),
                content_type='application/json'
            )
            response = drawing_extraction_webhook(request)
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(
                    f'    SUCCESS webhook failed: {response.status_code}'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'    Webhook processed successfully'
                ))
