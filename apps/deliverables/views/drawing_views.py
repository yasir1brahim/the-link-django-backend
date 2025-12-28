from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from ..models import (
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingExtractionWebhookEvent,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
)


@api_view(['POST'])
@permission_classes([AllowAny])
def drawing_extraction_webhook(request):
    """
    Webhook endpoint for receiving drawing extraction results from AWS Lambda.

    Idempotent: duplicate event_ids are ignored.
    Atomic: all changes within a single transaction.
    """
    payload = request.data
    event_id = payload.get('event_id')
    extraction_id = payload.get('extraction_id')
    new_status_str = payload.get('new_status')

    if not all([event_id, extraction_id, new_status_str]):
        return Response(
            {"error": "Missing required fields: event_id, extraction_id, new_status"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        new_status = DrawingExtractionStatus(new_status_str)
    except ValueError:
        return Response(
            {"error": f"Invalid status: {new_status_str}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        try:
            extraction = DrawingExtraction.objects.select_for_update().get(id=extraction_id)
        except DrawingExtraction.DoesNotExist:
            return Response(
                {"error": f"Extraction {extraction_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Try to record the webhook event for idempotency
        try:
            DrawingExtractionWebhookEvent.objects.create(
                extraction=extraction,
                event_id=event_id,
                new_status=new_status.value,
                output_s3_key=payload.get("output_s3_key"),
                payload=payload,
            )
        except IntegrityError:
            # Duplicate event_id - already processed
            return Response(status=status.HTTP_200_OK)

        # Status transition validation
        allowed_next_statuses = {
            DrawingExtractionStatus.PENDING: {
                DrawingExtractionStatus.PROCESSING,
                DrawingExtractionStatus.FAILED
            },
            DrawingExtractionStatus.PROCESSING: {
                DrawingExtractionStatus.SUCCESS,
                DrawingExtractionStatus.PARTIAL_SUCCESS,
                DrawingExtractionStatus.FAILED,
            },
            DrawingExtractionStatus.SUCCESS: set(),
            DrawingExtractionStatus.PARTIAL_SUCCESS: set(),
            DrawingExtractionStatus.FAILED: set(),
        }

        if new_status not in allowed_next_statuses.get(extraction.status, set()):
            # Ignore invalid transitions (e.g., PROCESSING after SUCCESS)
            return Response(status=status.HTTP_200_OK)

        # Process based on new status
        if new_status == DrawingExtractionStatus.PROCESSING:
            extraction.status = DrawingExtractionStatus.PROCESSING
            extraction.started_at = timezone.now()
            extraction.save()

        elif new_status in {DrawingExtractionStatus.SUCCESS, DrawingExtractionStatus.PARTIAL_SUCCESS}:
            extraction.status = new_status
            extraction.completed_at = timezone.now()
            extraction.model_version = payload.get('model_version')
            extraction.processing_time_ms = payload.get('processing_time_ms')
            extraction.output_s3_key = payload.get('output_s3_key')
            extraction.failure_summary = payload.get('failure_summary')
            extraction.save()

            # Update drawing file total_pages
            data = payload.get('data', {})
            if data.get('total_pages'):
                extraction.drawing_file.total_pages = data['total_pages']
                extraction.drawing_file.save()

            # Clear existing pages and recreate (idempotent)
            DrawingPage.objects.filter(extraction=extraction).delete()
            _create_drawing_records(extraction, data)

        elif new_status == DrawingExtractionStatus.FAILED:
            extraction.status = DrawingExtractionStatus.FAILED
            extraction.completed_at = timezone.now()
            extraction.error_message = payload.get('error_message')
            extraction.failure_summary = payload.get('failure_summary')
            extraction.save()

    return Response(status=status.HTTP_200_OK)


def _create_drawing_records(extraction, data):
    """
    Bulk create DrawingPage, DrawingNoteSection, and DrawingNote records.
    Uses bulk_create for performance on large PDFs.
    """
    pages_data = data.get('pages', [])

    # First pass: create all pages
    page_objects = []
    for page_data in pages_data:
        page_objects.append(DrawingPage(
            drawing_file=extraction.drawing_file,
            extraction=extraction,
            page_number=page_data['page_number'],
            page_type=page_data['page_type'],
            extraction_status=page_data['extraction_status'],
            spec_content=page_data.get('spec_content'),
        ))

    created_pages = DrawingPage.objects.bulk_create(page_objects)

    # Build page_number -> page mapping
    page_map = {p.page_number: p for p in created_pages}

    # Second pass: create all note sections
    section_objects = []
    section_notes_map = []  # Track (section_index, notes_data) for later

    for page_data in pages_data:
        page = page_map[page_data['page_number']]
        for section_data in page_data.get('note_sections', []):
            section_index = len(section_objects)
            section_objects.append(DrawingNoteSection(
                page=page,
                header=section_data['header'],
                header_bbox=section_data.get('header_bbox'),
            ))
            section_notes_map.append((section_index, section_data.get('notes', [])))

    created_sections = DrawingNoteSection.objects.bulk_create(section_objects)

    # Third pass: create all notes
    note_objects = []
    for section_index, notes_data in section_notes_map:
        section = created_sections[section_index]
        for note_data in notes_data:
            note_objects.append(DrawingNote(
                section=section,
                note_number=note_data['note_number'],
                category=note_data['category'],
                text=note_data['text'],
                bounding_box=note_data.get('bounding_box'),
                source_blocks=note_data.get('source_blocks'),
                drawing_references=note_data.get('drawing_references'),
            ))

    DrawingNote.objects.bulk_create(note_objects)
