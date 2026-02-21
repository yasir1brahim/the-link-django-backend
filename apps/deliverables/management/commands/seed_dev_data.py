"""
Seed a complete dev environment with users, project, drawings, and spec conflicts.

Usage:
    docker compose run --rm web python manage.py seed_dev_data
    docker compose run --rm web python manage.py seed_dev_data --flush
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken


class Command(BaseCommand):
    help = 'Seed complete dev data: users, team, project, drawings, spec conflicts'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete seeded data before recreating')

    def handle(self, *args, **options):
        from apps.users.models import CustomUser
        from apps.teams.models import Team, Membership
        from apps.deliverables.models import (
            Project, ProjectVersion, ProjectMembership,
            DrawingFile, DrawingExtraction, DrawingExtractionStatus,
            DrawingPage, DrawingPageExtractionStatus,
            DrawingNoteSection, DrawingNote,
            SpecComparison, SpecComparisonStatus, SpecConflict,
        )

        if options['flush']:
            self.stdout.write('Flushing seeded data...')
            SpecConflict.objects.filter(comparison__event_id='seed-comparison-001').delete()
            SpecComparison.objects.filter(event_id='seed-comparison-001').delete()
            DrawingFile.objects.filter(file_s3_key__startswith='test/drawings/').delete()
            Project.objects.filter(project_number='TCP-001').delete()
            Team.objects.filter(slug='dev-team').delete()
            CustomUser.objects.filter(email__in=['dev@thelink.ai', 'dev2@thelink.ai']).delete()
            self.stdout.write(self.style.SUCCESS('Flushed.'))

        with transaction.atomic():
            # Users
            user1, _ = CustomUser.objects.get_or_create(
                email='dev@thelink.ai',
                defaults={'username': 'dev', 'first_name': 'Dev', 'last_name': 'User'},
            )
            user1.set_password('devpassword123')
            user1.save()

            user2, _ = CustomUser.objects.get_or_create(
                email='dev2@thelink.ai',
                defaults={'username': 'dev2', 'first_name': 'Jane', 'last_name': 'Smith'},
            )
            user2.set_password('devpassword123')
            user2.save()

            # Team
            team, _ = Team.objects.get_or_create(name='Dev Team', slug='dev-team')
            Membership.objects.get_or_create(team=team, user=user1, defaults={'role': 'admin'})
            Membership.objects.get_or_create(team=team, user=user2, defaults={'role': 'member'})

            # Project (auto-creates ProjectVersion 1 via save())
            project, created = Project.objects.get_or_create(
                project_number='TCP-001',
                defaults={'name': 'Test Construction Project', 'team': team, 'created_by': user1},
            )
            version = project.versions.first()

            # Project membership
            ProjectMembership.objects.get_or_create(project=project, user=user1, defaults={'role': 'project_admin'})
            ProjectMembership.objects.get_or_create(project=project, user=user2, defaults={'role': 'project_admin'})

            # Drawing file
            df, _ = DrawingFile.objects.get_or_create(
                file_s3_key='test/drawings/arch-v1.pdf',
                defaults={
                    'project': project, 'project_version': version,
                    'file_name': 'architectural-drawings-v1.pdf', 'md5': 'abc123', 'total_pages': 3,
                },
            )

            # Extraction
            ext, _ = DrawingExtraction.objects.get_or_create(
                drawing_file=df,
                defaults={'status': DrawingExtractionStatus.SUCCESS, 'model_version': 'seed-v1'},
            )

            # Pages
            pages_data = [
                ('A-101', 'First Floor Plan', 1),
                ('A-102', 'Second Floor Plan', 2),
                ('S-201', 'Structural Foundation', 3),
            ]
            pages = []
            for sheet_num, sheet_title, page_num in pages_data:
                p, _ = DrawingPage.objects.get_or_create(
                    drawing_file=df, page_number=page_num,
                    defaults={
                        'extraction': ext, 'page_type': 'DRAWING',
                        'extraction_status': DrawingPageExtractionStatus.SUCCESS,
                        'sheet_number': sheet_num, 'sheet_title': sheet_title,
                        'rotated_width': 792.0, 'rotated_height': 612.0,
                        'unrotated_width': 792.0, 'unrotated_height': 612.0,
                    },
                )
                pages.append(p)

            # Sections
            sections = []
            for p in pages:
                s, _ = DrawingNoteSection.objects.get_or_create(
                    page=p, header='GENERAL NOTES',
                )
                sections.append(s)

            # Drawing notes
            notes_data = [
                (0, 'All conduit shall be buried minimum 30 inches below finished grade', [100, 200, 500, 230], 'ELECTRICAL'),
                (0, 'Concrete shall achieve minimum 4000 PSI compressive strength at 28 days', [100, 250, 500, 280], 'STRUCTURAL'),
                (1, 'All structural steel connections shall be designed per AISC 360-16', [100, 200, 500, 230], 'STRUCTURAL'),
                (1, 'Fire-rated assemblies shall maintain minimum 2-hour rating per IBC 2021', [100, 250, 500, 280], 'FIRE PROTECTION'),
                (2, 'Waterproofing membrane shall extend minimum 12 inches above finished grade', [100, 200, 500, 230], 'WATERPROOFING'),
                (2, 'All electrical panels shall maintain 36-inch clearance per NEC 110.26', [100, 250, 500, 280], 'ELECTRICAL'),
            ]
            notes = []
            for idx, (sec_idx, text, bbox, category) in enumerate(notes_data):
                n, _ = DrawingNote.objects.get_or_create(
                    section=sections[sec_idx], text=text,
                    defaults={
                        'note_number': idx + 1, 'category': category,
                        'bounding_box': bbox, 'unrotated_bounding_box': bbox,
                    },
                )
                notes.append(n)

            # Spec comparison
            now = timezone.now()
            comp, _ = SpecComparison.objects.get_or_create(
                event_id='seed-comparison-001',
                defaults={
                    'project': project, 'project_version': version,
                    'triggered_by': user1, 'status': SpecComparisonStatus.SUCCESS,
                    'started_at': now, 'completed_at': now,
                    'notes_processed': 6, 'notes_with_mismatch': 5,
                },
            )

            # Spec conflicts
            conflicts_data = [
                (notes[0], 'Conduit burial depth shall be minimum 24 inches below grade', 'test/specs/div-26.pdf', 5, '26 05 00', 0.92,
                 'Drawing requires 30" burial depth but spec only requires 24"',
                 [{'page_no': 5, 'x': 72, 'y': 300, 'width': 400, 'height': 40}]),
                (notes[1], 'Concrete compressive strength shall be minimum 3000 PSI at 28 days', 'test/specs/div-03.pdf', 12, '03 30 00', 0.88,
                 'Drawing specifies 4000 PSI but spec only requires 3000 PSI',
                 [{'page_no': 12, 'x': 72, 'y': 200, 'width': 400, 'height': 40}]),
                (notes[2], 'Steel connections per AISC 360-10 (2010 edition)', 'test/specs/div-05.pdf', 8, '05 12 00', 0.85,
                 'Drawing references AISC 360-16 but spec references older 360-10 edition',
                 [{'page_no': 8, 'x': 72, 'y': 150, 'width': 400, 'height': 40}]),
                (notes[3], 'Fire-rated assemblies shall maintain minimum 1-hour rating', 'test/specs/div-07.pdf', 3, '07 84 00', 0.95,
                 'Drawing requires 2-hour fire rating but spec only requires 1-hour',
                 [{'page_no': 3, 'x': 72, 'y': 250, 'width': 400, 'height': 40}]),
                (notes[4], 'Waterproofing membrane shall extend minimum 6 inches above grade', 'test/specs/div-07.pdf', 15, '07 10 00', 0.78,
                 'Drawing requires 12" extension but spec only requires 6"',
                 [{'page_no': 15, 'x': 72, 'y': 350, 'width': 400, 'height': 40}]),
            ]
            for note, spec_text, s3_key, page_no, mf_num, confidence, reason, locations in conflicts_data:
                SpecConflict.objects.get_or_create(
                    comparison=comp, note=note,
                    defaults={
                        'note_id_from_lambda': str(note.id),
                        'note_text': note.text,
                        'spec_text': spec_text,
                        'spec_file_s3_key': s3_key,
                        'spec_page_number': page_no,
                        'spec_masterformat_number': mf_num,
                        'confidence': confidence,
                        'reason': reason,
                        'pdf_locations': locations,
                    },
                )

        # Generate token
        refresh = RefreshToken.for_user(user1)
        token = str(refresh.access_token)

        self.stdout.write(self.style.SUCCESS(f'''
========================================
  Dev Data Seeded Successfully!
========================================
Users:
  dev@thelink.ai / devpassword123
  dev2@thelink.ai / devpassword123

Project: {project.name} (TCP-001) [id={project.id}]
  Version: {version.version_name} [id={version.id}]
  Drawing Notes: {len(notes)}
  Spec Conflicts: {len(conflicts_data)}

Auth Token (dev@thelink.ai):
  Bearer {token}

Example curls:
  curl -H "Authorization: Bearer {token}" http://localhost:8000/api/deliverables/projects/{project.id}/spec-conflicts/?project_version_id={version.id}
  curl -X PATCH -H "Authorization: Bearer {token}" -H "Content-Type: application/json" -d '{{"status":"RFI"}}' http://localhost:8000/api/deliverables/projects/{project.id}/spec-conflicts/<conflict_id>/status/
========================================
'''))
