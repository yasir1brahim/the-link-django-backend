from django.db import transaction, IntegrityError
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.pagination import PageNumberPagination

from ..models import (
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingExtractionWebhookEvent,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
    DrawingFile,
)
from ..serializers.drawing_serializers import DrawingNoteReadSerializer
from ..permissions import DrawingNoteAccessPermissions


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


class DrawingNotePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'limit'
    max_page_size = 100


class DrawingNoteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for listing drawing notes.
    Mirrors SubmittalItemViewSet pattern with filtering and pagination.
    """
    permission_classes = [IsAuthenticated, DrawingNoteAccessPermissions]
    pagination_class = DrawingNotePagination
    serializer_class = DrawingNoteReadSerializer

    def get_queryset(self):
        project_id = self.kwargs['project_id']
        queryset = DrawingNote.objects.filter(
            section__page__drawing_file__project_id=project_id
        ).select_related(
            'section__page__drawing_file',
            'section__page__extraction',
        )

        # Filter by project_version_id
        version_id = self.request.query_params.get('project_version_id')
        if version_id:
            queryset = queryset.filter(
                section__page__drawing_file__project_version_id=version_id
            )

        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by drawing_file_id
        drawing_file_id = self.request.query_params.get('drawing_file_id')
        if drawing_file_id:
            queryset = queryset.filter(
                section__page__drawing_file_id=drawing_file_id
            )

        # Search in text (case-insensitive substring)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(text__icontains=search)

        return queryset

    def _get_processing_status(self, project_id, version_id=None):
        """
        Get processing status for all drawing files in the project/version.
        Returns status object with file counts and details for files still processing.
        """
        # Get all drawing files for this project/version
        files_qs = DrawingFile.objects.filter(project_id=project_id)
        if version_id:
            files_qs = files_qs.filter(project_version_id=version_id)

        # Annotate with latest extraction status
        latest_extraction = DrawingExtraction.objects.filter(
            drawing_file=OuterRef('pk')
        ).order_by('-created_at')

        files_with_status = files_qs.annotate(
            latest_status=Subquery(latest_extraction.values('status')[:1])
        )

        # Count by status
        files_processing = 0
        files_completed = 0
        files_failed = 0
        processing_files = []

        for f in files_with_status:
            file_status = f.latest_status
            if file_status in [DrawingExtractionStatus.PENDING, DrawingExtractionStatus.PROCESSING]:
                files_processing += 1
                processing_files.append({
                    'id': f.id,
                    'name': f.file_name,
                    'status': file_status or DrawingExtractionStatus.PENDING,
                })
            elif file_status in [DrawingExtractionStatus.SUCCESS, DrawingExtractionStatus.PARTIAL_SUCCESS]:
                files_completed += 1
            elif file_status == DrawingExtractionStatus.FAILED:
                files_failed += 1
            elif file_status is None:
                # No extraction yet - treat as pending
                files_processing += 1
                processing_files.append({
                    'id': f.id,
                    'name': f.file_name,
                    'status': DrawingExtractionStatus.PENDING,
                })

        return {
            'is_processing': files_processing > 0,
            'files_processing': files_processing,
            'files_completed': files_completed,
            'files_failed': files_failed,
            'files': processing_files,
        }

    def list(self, request, *args, **kwargs):
        project_id = self.kwargs['project_id']
        version_id = request.query_params.get('project_version_id')

        queryset = self.filter_queryset(self.get_queryset())

        # Get filter values for UI dropdowns
        # Get unique drawing files with id and name
        drawing_files_qs = DrawingFile.objects.filter(
            pages__note_sections__notes__in=queryset
        ).distinct().values('id', 'file_name')

        all_filter_vals = {
            'category': list(set(queryset.values_list('category', flat=True))),
            'drawing_files': [{'id': df['id'], 'name': df['file_name']} for df in drawing_files_qs],
        }

        # Get processing status
        processing_status = self._get_processing_status(project_id, version_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['all_filter_vals'] = all_filter_vals
            response.data['total_count'] = queryset.count()
            response.data['processing_status'] = processing_status
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'all_filter_vals': all_filter_vals,
            'total_count': queryset.count(),
            'processing_status': processing_status,
        })
