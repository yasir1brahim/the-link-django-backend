import boto3
from django.conf import settings
from rest_framework import serializers

from ..models import (
    SpecComparison,
    SpecComparisonStatus,
    SpecConflict,
    SpecConflictComment,
    SkippedNote,
    SkipReason,
)


# Initialize S3 client at module level (matches existing pattern)
s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


# --- Webhook Payload Serializers (for validating incoming lambda data) ---


class PdfLocationSerializer(serializers.Serializer):
    """Validates PDF bounding box location data"""
    page_no = serializers.IntegerField()
    x = serializers.FloatField()
    y = serializers.FloatField()
    width = serializers.FloatField()
    height = serializers.FloatField()


class SpecConflictPayloadSerializer(serializers.Serializer):
    """Validates conflict data from lambda webhook payload"""
    note_id = serializers.CharField()
    note_text = serializers.CharField()
    spec_text = serializers.CharField()
    spec_source_file = serializers.CharField()
    spec_page_number = serializers.IntegerField(min_value=1)
    spec_masterformat_number = serializers.CharField()
    confidence = serializers.FloatField(min_value=0.0, max_value=1.0)
    reason = serializers.CharField()
    pdf_locations = PdfLocationSerializer(many=True, required=False, default=list)

    def validate_spec_source_file(self, value):
        """Enforce s3://{bucket}/{key} URI format and validate bucket matches our bucket."""
        if not value.startswith('s3://'):
            raise serializers.ValidationError(
                f"spec_source_file must be an s3:// URI, got: {value[:50]}"
            )
        # Validate format: s3://bucket/key (must have bucket AND key)
        parts = value[5:].split('/', 1)  # Remove 's3://'
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise serializers.ValidationError(
                f"spec_source_file must be s3://bucket/key format, got: {value[:50]}"
            )
        # Security: validate bucket matches our expected bucket (skip if S3_BUCKET not configured)
        bucket = parts[0]
        if settings.S3_BUCKET and bucket != settings.S3_BUCKET:
            raise serializers.ValidationError(
                f"spec_source_file bucket must be {settings.S3_BUCKET}, got: {bucket}"
            )
        return value


class SkippedNotePayloadSerializer(serializers.Serializer):
    """Validates skipped note data from lambda webhook payload"""
    note_id = serializers.CharField()
    disciplines = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    sheet_discipline = serializers.CharField(required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=SkipReason.choices)
    detail = serializers.CharField(required=False, allow_null=True)


class SpecComparisonWebhookDataSerializer(serializers.Serializer):
    """Validates the nested 'data' object from lambda webhook payload"""
    conflicts = SpecConflictPayloadSerializer(many=True, required=False, default=list)
    skipped_notes = SkippedNotePayloadSerializer(many=True, required=False, default=list)
    notes_processed = serializers.IntegerField(required=False, default=0, min_value=0)
    notes_skipped = serializers.IntegerField(required=False, default=0, min_value=0)
    # Lambda sends 'specs_processed', we map to 'spec_files_processed' for model compatibility
    specs_processed = serializers.IntegerField(required=False, default=0, min_value=0)
    notes_with_mismatch = serializers.IntegerField(required=False, default=0, min_value=0)
    error_message = serializers.CharField(required=False, allow_null=True)


class SpecComparisonWebhookSerializer(serializers.Serializer):
    """Validates the complete webhook payload from lambda.

    Lambda sends:
    {
        "event_id": "...",
        "status": "SUCCESS",
        "comparison_id": 9,
        "data": {
            "conflicts": [...],
            "skipped_notes": [...],
            "notes_processed": 32,
            ...
        }
    }
    """
    event_id = serializers.CharField(required=True, allow_blank=False)
    comparison_id = serializers.IntegerField(required=True)
    status = serializers.ChoiceField(choices=[
        SpecComparisonStatus.SUCCESS,
        SpecComparisonStatus.PARTIAL_SUCCESS,
        SpecComparisonStatus.FAILED,
    ])  # Only terminal statuses allowed
    data = SpecComparisonWebhookDataSerializer(required=True)

    def to_internal_value(self, data):
        """Flatten the nested 'data' field into top-level for easier access in view."""
        result = super().to_internal_value(data)
        # Flatten nested data into top-level
        nested_data = result.pop('data', {})
        result['conflicts'] = nested_data.get('conflicts', [])
        result['skipped_notes'] = nested_data.get('skipped_notes', [])
        result['notes_processed'] = nested_data.get('notes_processed', 0)
        result['notes_skipped'] = nested_data.get('notes_skipped', 0)
        # Map 'specs_processed' from lambda to 'spec_files_processed' for model
        result['spec_files_processed'] = nested_data.get('specs_processed', 0)
        result['notes_with_mismatch'] = nested_data.get('notes_with_mismatch', 0)
        result['error_message'] = nested_data.get('error_message')
        return result


# --- Read Serializers (for API responses) ---


class SpecComparisonSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for comparison metadata in responses"""

    class Meta:
        model = SpecComparison
        fields = ['id', 'status', 'completed_at']


class SpecConflictReadSerializer(serializers.ModelSerializer):
    """Serializer for reading conflict data via API"""
    note_id = serializers.SerializerMethodField()
    spec_file_url = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    # Drawing-related fields
    sheet_number = serializers.SerializerMethodField()
    sheet_title = serializers.SerializerMethodField()
    drawing_file_url = serializers.SerializerMethodField()
    drawing_page_number = serializers.SerializerMethodField()
    drawing_bounding_box = serializers.SerializerMethodField()

    class Meta:
        model = SpecConflict
        fields = [
            'id',
            'note_id',
            'note_id_from_lambda',
            'note_text',
            'status',
            'comment_count',
            # Drawing fields
            'sheet_number',
            'sheet_title',
            'drawing_file_url',
            'drawing_page_number',
            'drawing_bounding_box',
            # Spec fields
            'spec_text',
            'spec_file_s3_key',
            'spec_file_url',
            'spec_page_number',
            'spec_masterformat_number',
            'confidence',
            'reason',
            'pdf_locations',
        ]

    def get_note_id(self, obj):
        """Return note.id if FK exists, otherwise fall back to note_id_from_lambda."""
        if obj.note:
            return obj.note.id
        # Fall back to lambda-provided ID (may be string for non-integer IDs)
        return obj.note_id_from_lambda

    def get_sheet_number(self, obj):
        """Get sheet number from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.sheet_number
        return None

    def get_sheet_title(self, obj):
        """Get sheet title from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.sheet_title
        return None

    def get_drawing_file_url(self, obj):
        """Generate presigned S3 URL for drawing file access."""
        if not obj.note or not obj.note.section or not obj.note.section.page:
            return None

        drawing_file = obj.note.section.page.drawing_file
        s3_key = drawing_file.file_s3_key

        # Memoize URLs per s3_key within request context
        context = self.context
        cache_key = 'presigned_urls'
        if cache_key not in context:
            context[cache_key] = {}

        if s3_key not in context[cache_key]:
            context[cache_key][s3_key] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
                ExpiresIn=3600,
            )
        return context[cache_key][s3_key]

    def get_drawing_page_number(self, obj):
        """Get page number from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.page_number
        return None

    def get_drawing_bounding_box(self, obj):
        """Get bounding box for the note in the drawing."""
        if obj.note:
            # Prefer unrotated_bounding_box, fall back to bounding_box
            return obj.note.unrotated_bounding_box or obj.note.bounding_box
        return None

    def get_spec_file_url(self, obj):
        """Generate presigned S3 URL for spec file access."""
        # Memoize URLs per s3_key within request context to avoid redundant S3 calls
        context = self.context
        cache_key = 'presigned_urls'
        if cache_key not in context:
            context[cache_key] = {}

        s3_key = obj.spec_file_s3_key
        if s3_key not in context[cache_key]:
            context[cache_key][s3_key] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
                ExpiresIn=3600,
            )
        return context[cache_key][s3_key]

    def get_comment_count(self, obj):
        """Get comment count for this conflict."""
        # Use annotated count if available (from queryset with annotate),
        # otherwise fall back to counting (less efficient)
        if hasattr(obj, 'comment_count_annotated'):
            return obj.comment_count_annotated
        return obj.comments.count()


class SkippedNoteReadSerializer(serializers.ModelSerializer):
    """Serializer for reading skipped note data via API"""
    note_id = serializers.SerializerMethodField()

    class Meta:
        model = SkippedNote
        fields = [
            'id',
            'note_id',
            'note_id_from_lambda',
            'disciplines',
            'sheet_discipline',
            'reason',
            'detail',
        ]

    def get_note_id(self, obj):
        """Return note.id if FK exists, otherwise fall back to note_id_from_lambda."""
        if obj.note:
            return obj.note.id
        return obj.note_id_from_lambda


class SpecComparisonListSerializer(serializers.ModelSerializer):
    """Serializer for listing comparison runs"""
    triggered_by = serializers.SerializerMethodField()
    conflict_count = serializers.SerializerMethodField()

    class Meta:
        model = SpecComparison
        fields = [
            'id',
            'status',
            'event_id',
            'created_at',
            'started_at',
            'completed_at',
            'triggered_by',
            'notes_processed',
            'notes_skipped',
            'spec_files_processed',
            'conflict_count',
        ]

    def get_triggered_by(self, obj):
        if obj.triggered_by:
            return {'display_name': obj.triggered_by.get_full_name() or obj.triggered_by.email}
        return None

    def get_conflict_count(self, obj):
        # Use annotated count if available (from queryset with annotate),
        # otherwise fall back to counting (less efficient)
        if hasattr(obj, 'conflict_count_annotated'):
            return obj.conflict_count_annotated
        return obj.conflicts.count()


class TriggerSpecComparisonSerializer(serializers.Serializer):
    """Serializer for trigger endpoint request"""
    project_version_id = serializers.IntegerField(required=True)


class TriggerSpecComparisonResponseSerializer(serializers.ModelSerializer):
    """Serializer for trigger endpoint response"""
    triggered_by = serializers.SerializerMethodField()

    class Meta:
        model = SpecComparison
        fields = [
            'id',
            'status',
            'event_id',
            'created_at',
            'started_at',
            'triggered_by',
        ]

    def get_triggered_by(self, obj):
        if obj.triggered_by:
            return {
                'id': obj.triggered_by.id,
                'display_name': obj.triggered_by.get_full_name() or obj.triggered_by.email,
            }
        return None


class SpecConflictCommentSerializer(serializers.ModelSerializer):
    """Serializer for spec conflict comments"""
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = SpecConflictComment
        fields = ['id', 'text', 'user_id', 'user_full_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user_id', 'user_full_name', 'created_at', 'updated_at']
