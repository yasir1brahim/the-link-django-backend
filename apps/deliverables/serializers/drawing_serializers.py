import boto3
from django.conf import settings
from rest_framework import serializers
from ..models import DrawingNote, DrawingPageExtractionStatus


s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


class DrawingNoteReadSerializer(serializers.ModelSerializer):
    """
    Flattened serializer for DrawingNote table display.
    Includes related fields from section, page, and drawing file.
    """
    # Flattened fields for table display
    drawing_file_id = serializers.IntegerField(source='section.page.drawing_file.id')
    drawing_file_name = serializers.CharField(source='section.page.drawing_file.file_name')
    drawing_file_url = serializers.SerializerMethodField()
    page_number = serializers.IntegerField(source='section.page.page_number')
    page_rotation = serializers.IntegerField(source='section.page.rotation')
    page_rotated_width = serializers.FloatField(source='section.page.rotated_width')
    page_rotated_height = serializers.FloatField(source='section.page.rotated_height')
    page_unrotated_width = serializers.FloatField(source='section.page.unrotated_width')
    page_unrotated_height = serializers.FloatField(source='section.page.unrotated_height')
    section_header = serializers.CharField(source='section.header')
    section_rotated_header_bbox = serializers.JSONField(source='section.rotated_header_bbox')
    section_unrotated_header_bbox = serializers.JSONField(source='section.unrotated_header_bbox')

    # Extraction status for error display
    page_extraction_status = serializers.CharField(source='section.page.extraction_status')
    page_extraction_failed = serializers.SerializerMethodField()

    class Meta:
        model = DrawingNote
        fields = [
            'id',
            'drawing_file_id',
            'drawing_file_name',
            'drawing_file_url',
            'page_number',
            'page_rotation',
            'page_rotated_width',
            'page_rotated_height',
            'page_unrotated_width',
            'page_unrotated_height',
            'section_header',
            'section_rotated_header_bbox',
            'section_unrotated_header_bbox',
            'note_number',
            'category',
            'text',
            'drawing_references',
            'bounding_box',
            'raw_bounding_box',
            'rotated_bounding_box',
            'unrotated_bounding_box',
            'page_extraction_status',
            'page_extraction_failed',
        ]

    def get_drawing_file_url(self, obj):
        """Generate a presigned URL for the drawing file PDF."""
        s3_key = obj.section.page.drawing_file.file_s3_key
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
            ExpiresIn=3600
        )

    def get_page_extraction_failed(self, obj):
        return obj.section.page.extraction_status == DrawingPageExtractionStatus.FAILED
