import logging
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import (
    SpecComparison,
    SpecComparisonStatus,
    SpecComparisonWebhookEvent,
    SpecConflict,
    SkippedNote,
    DrawingNote,
)
from ..serializers.spec_comparison_serializers import (
    SpecComparisonWebhookSerializer,
)

logger = logging.getLogger(__name__)


def parse_s3_uri_to_key(s3_uri: str) -> str:
    """Extract S3 key from s3://bucket/key URI.

    Only accepts s3:// URIs (validated by serializer).
    """
    # s3://bucket/path/to/file.pdf -> path/to/file.pdf
    parts = s3_uri[5:].split('/', 1)  # Remove 's3://'
    if len(parts) > 1:
        return parts[1]
    raise ValueError(f"Invalid S3 URI format: {s3_uri}")


def safe_int(value: str) -> int | None:
    """Safely convert string to int, return None if invalid."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def verify_webhook_signature(request) -> bool:
    """Verify HMAC signature from lambda webhook.

    Lambda should send signature in X-Webhook-Signature header as:
    sha256=<hex_digest>

    The signature is computed as HMAC-SHA256 of the request body using
    SPEC_COMPARISON_WEBHOOK_SECRET as the key.

    SECURITY: Fails closed in production (DEBUG=False) when secret is not configured.
    """
    import hmac
    import hashlib

    secret = settings.SPEC_COMPARISON_WEBHOOK_SECRET
    if not secret:
        # Fail closed in production - require secret to be configured
        if not settings.DEBUG:
            logger.error("SPEC_COMPARISON_WEBHOOK_SECRET not set in production - rejecting webhook")
            return False
        # In development (DEBUG=True), allow requests but warn
        logger.warning("SPEC_COMPARISON_WEBHOOK_SECRET not set - webhook authentication disabled (dev only)")
        return True

    signature_header = request.headers.get('X-Webhook-Signature', '')
    if not signature_header.startswith('sha256='):
        return False

    expected_signature = signature_header[7:]  # Remove 'sha256=' prefix
    body = request.body

    computed_signature = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)


@api_view(['POST'])
@permission_classes([AllowAny])
def spec_comparison_webhook(request):
    """
    Webhook endpoint for receiving spec comparison results from AWS Lambda.
    Idempotent: duplicate event_ids are ignored.
    Atomic: all changes within a single transaction.
    Authenticated: HMAC signature verified if SPEC_COMPARISON_WEBHOOK_SECRET is set.
    """
    # Verify webhook signature (HMAC authentication)
    if not verify_webhook_signature(request):
        return Response(
            {"error": "Invalid webhook signature"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Validate payload
    serializer = SpecComparisonWebhookSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Invalid payload", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data
    event_id = data['event_id']
    comparison_id = data['comparison_id']
    new_status = data['status']

    with transaction.atomic():
        # Lock comparison row to prevent races
        try:
            comparison = SpecComparison.objects.select_for_update().get(id=comparison_id)
        except SpecComparison.DoesNotExist:
            return Response(
                {"error": "Comparison not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify event_id matches
        if comparison.event_id != event_id:
            return Response(
                {"error": "Event ID mismatch"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create webhook event for idempotency (unique constraint on event_id)
        try:
            SpecComparisonWebhookEvent.objects.create(
                comparison=comparison,
                event_id=event_id,
                new_status=new_status,
            )
        except IntegrityError:
            # Duplicate event_id - already processed
            return Response({"status": "already_processed"}, status=status.HTTP_200_OK)

        # Update comparison metadata
        comparison.status = new_status
        comparison.notes_processed = data['notes_processed']
        comparison.notes_skipped = data['notes_skipped']
        comparison.spec_files_processed = data['spec_files_processed']
        comparison.notes_with_mismatch = data['notes_with_mismatch']
        comparison.completed_at = timezone.now()

        if new_status == SpecComparisonStatus.FAILED:
            comparison.error_message = data.get('error_message')
            comparison.save()
            # FAILED: Do not store conflicts/skipped notes (no partial data)
            return Response({"status": "processed"}, status=status.HTTP_200_OK)

        comparison.save()

        # SUCCESS/PARTIAL_SUCCESS: Store conflicts and skipped notes

        # Build note ID lookup for FK linking (safely handle non-integer IDs)
        conflict_note_ids = [c['note_id'] for c in data['conflicts']]
        skipped_note_ids = [s['note_id'] for s in data['skipped_notes']]
        all_note_ids_raw = set(conflict_note_ids + skipped_note_ids)

        # Safely convert to integers, filtering out invalid IDs
        valid_note_ids = [safe_int(nid) for nid in all_note_ids_raw]
        valid_note_ids = [nid for nid in valid_note_ids if nid is not None]

        notes_by_id = {}
        if valid_note_ids:
            # Scope note lookup to the comparison's project/version for security
            notes_by_id = {
                str(n.id): n
                for n in DrawingNote.objects.filter(
                    id__in=valid_note_ids,
                    section__page__extraction__drawing_file__project=comparison.project,
                    section__page__extraction__drawing_file__project_version=comparison.project_version,
                )
            }

        # Create conflicts (with batch_size for large lists)
        if data['conflicts']:
            conflicts_to_create = [
                SpecConflict(
                    comparison=comparison,
                    note=notes_by_id.get(c['note_id']),
                    note_id_from_lambda=c['note_id'],
                    note_text=c['note_text'],
                    spec_text=c['spec_text'],
                    spec_file_s3_key=parse_s3_uri_to_key(c['spec_source_file']),
                    spec_page_number=c['spec_page_number'],
                    spec_masterformat_number=c['spec_masterformat_number'],
                    confidence=c['confidence'],
                    reason=c['reason'],
                    pdf_locations=c.get('pdf_locations', []),
                )
                for c in data['conflicts']
            ]
            SpecConflict.objects.bulk_create(conflicts_to_create, batch_size=500)

        # Create skipped notes (with batch_size for large lists)
        if data['skipped_notes']:
            skipped_to_create = [
                SkippedNote(
                    comparison=comparison,
                    note=notes_by_id.get(s['note_id']),
                    note_id_from_lambda=s['note_id'],
                    disciplines=s.get('disciplines', []),
                    sheet_discipline=s.get('sheet_discipline'),
                    reason=s['reason'],
                    detail=s.get('detail'),
                )
                for s in data['skipped_notes']
            ]
            SkippedNote.objects.bulk_create(skipped_to_create, batch_size=500)

    return Response({"status": "processed"}, status=status.HTTP_200_OK)
