from django.db.models import F, OuterRef, Q, Subquery
from rest_framework import serializers
from ..models import (
    SpecSection,
    SubmittalItem,
    MasterFormatSection,
    Project,
    ProjectVersion,
    UploadedFile,
    AiGeneratedLog,
    ExtractedData
)
from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active


class SpecSectionSerializer(serializers.ModelSerializer):
    """Serializer for spec sections with basic information."""
    masterformat_number = serializers.CharField(source='masterformat_section.masterformat_number', read_only=True)
    masterformat_title = serializers.CharField(source='masterformat_section.title', read_only=True)
    document_name = serializers.CharField(source='document.name', read_only=True)
    document_id = serializers.IntegerField(source='document.id', read_only=True)
    pdf_url = serializers.SerializerMethodField()
    
    def get_pdf_url(self, obj):
        """Get presigned S3 URL for the spec section."""
        if obj.file_s3_key:
            from django.conf import settings
            import boto3
            
            try:
                # Use the same S3 client pattern as other serializers
                s3 = boto3.client('s3')
                presigned_url = s3.generate_presigned_url(
                    'get_object', 
                    Params={'Bucket': settings.S3_BUCKET, 'Key': obj.file_s3_key}, 
                    ExpiresIn=3600
                )
                return presigned_url
            except Exception as e:
                # If presigned URL generation fails, return the raw S3 key
                return obj.file_s3_key
        return None
    
    class Meta:
        model = SpecSection
        fields = [
            'id',
            'masterformat_number',
            'masterformat_title',
            'custom_section_title',
            'document_name',
            'document_id',
            'pdf_url',
            'processing_status',
            'processing_method',
            'specgpt_embedding_status',
            'file_s3_key'
        ]


class SubmittalHighlightSerializer(serializers.ModelSerializer):
    """Serializer for submittal items with highlight positioning data."""
    spec_section_title = serializers.CharField(source='spec_section.custom_section_title', read_only=True)
    masterformat_number = serializers.CharField(source='masterformat_section.masterformat_number', read_only=True)
    document_id = serializers.IntegerField(source='document.id', read_only=True)
    
    class Meta:
        model = SubmittalItem
        fields = [
            'id',
            'paragraph_number',
            'heirarchical_paragraph_number',
            'text_location',
            'additional_text_locations',
            'spec_section_title',
            'masterformat_number',
            'document_id',
            'parsing_method',
            'parsing_version'
        ]


class SpecSectionContentSerializer(serializers.Serializer):
    """Serializer for spec section content with submittal highlights and AI log highlights."""
    spec_section = SpecSectionSerializer(read_only=True)
    content = serializers.CharField(read_only=True)
    submittal_highlights = SubmittalHighlightSerializer(many=True, read_only=True)
    ai_log_highlights = serializers.SerializerMethodField()

    def _normalize_item_type(self, item_type):
        """
        Normalize item type to code format (lowercase with underscores).
        Converts display labels like 'Inspection' or 'Inspections' to 'inspections'.
        """
        if not item_type:
            return ''
        
        # Mapping from various display formats to canonical code format
        item_type_mapping = {
            'inspection': 'inspections',
            'inspections': 'inspections',
            'warranty': 'warranties',
            'warranties': 'warranties',
            'certificate': 'certificates',
            'certificates': 'certificates',
            'closeout submittal': 'closeout_submittals',
            'closeout submittals': 'closeout_submittals',
            'test report': 'test_reports',
            'test reports': 'test_reports',
            'commissioning': 'commissioning',
            'delegated design': 'delegated_design',
            'mock-up': 'mock_ups_sample_construction',
            'mock-ups': 'mock_ups_sample_construction',
            'mock-ups/sample construction': 'mock_ups_sample_construction',
            'sample construction': 'mock_ups_sample_construction',
            'pre-installation meeting': 'pre_installation_meetings',
            'pre-installation meetings': 'pre_installation_meetings',
        }
        
        # Normalize to lowercase for lookup
        normalized_key = item_type.lower().strip()
        
        # Return the canonical format or the original if not found in mapping
        return item_type_mapping.get(normalized_key, item_type.lower().replace(' ', '_').replace('-', '_'))
    
    def fuzzy_match_spec_section_number(self, spec_section_number_from_ai_log, spec_section_number_from_spec_section):
        """Fuzzy match the spec section number from the AI log to the spec section number from the spec section."""
        import re
        
        def normalize_spec_section(spec_section):
            """Strip whitespace and non-numerical characters, then convert to int."""
            if not spec_section:
                return None
            # Remove all whitespace and non-numerical characters
            numeric_only = re.sub(r'[^\d]', '', str(spec_section))
            return numeric_only
        
        # Normalize both spec section numbers
        ai_log_normalized = normalize_spec_section(spec_section_number_from_ai_log)
        spec_section_normalized = normalize_spec_section(spec_section_number_from_spec_section)
        
        # Return True if both normalize to the same integer, False otherwise
        return (ai_log_normalized is not None and 
                spec_section_normalized is not None and 
                ai_log_normalized == spec_section_normalized)
        
    
    def get_ai_log_highlights(self, obj):
        """Get highlights from ExtractedData model (both AI and human-created)"""
        # Handle both dictionary and model instance formats
        if isinstance(obj, dict):
            # Instance is a dictionary with 'spec_section' key
            spec_section = obj.get('spec_section')
            spec_section_id = spec_section.id if spec_section else None
        else:
            # Instance is a model object (SpecSection)
            spec_section_id = obj.id

        if not spec_section_id:
            return []

        # Subquery to fetch the latest AI log per extraction type for this spec section
        latest_log_subquery = AiGeneratedLog.objects.filter(
            extracted_items__spec_section_id=spec_section_id,
            log_type=OuterRef('extraction_type'),
        ).order_by('-created_at').values('id')[:1]

        # Query ExtractedData directly using spec_section FK and limit AI items to the latest logs
        extracted_items = ExtractedData.objects.filter(
            spec_section_id=spec_section_id,
            pdf_locations__isnull=False  # Only items with PDF locations
        ).annotate(
            latest_log_id=Subquery(latest_log_subquery)
        ).filter(
            Q(ai_generated_log__isnull=True) | Q(ai_generated_log_id=F('latest_log_id'))
        ).select_related('created_by').prefetch_related('notes__created_by')

        # Format results
        results = []
        for item in extracted_items:
            metadata = item.metadata or {}
            result = {
                'id': item.id,
                'extraction_type': item.extraction_type,
                'item_type': item.item_type,
                'spec_section_number': item.spec_section_number,
                'spec_section_name': item.spec_section_name,
                'requirement_text': item.requirement_text,
                'responsible_party': item.responsible_party,
                'metadata': metadata,
                'pdf_locations': item.pdf_locations,

                # Include source information
                'source': item.source,
                'source_display': item.get_source_display(),
                'created_by': item.created_by.get_full_name() if item.created_by else None,
                'created_by_id': item.created_by.id if item.created_by else None,
                'created_at': item.created_at.isoformat() if item.created_at else None,

                # Include notes
                'notes': [
                    {
                        'id': note.id,
                        'text': note.text,
                        'created_by_id': note.created_by.id if note.created_by else None,
                        'created_by_name': note.created_by.get_full_name() if note.created_by else None,
                        'created_at': note.created_at.isoformat() if note.created_at else None,
                        'updated_at': note.updated_at.isoformat() if note.updated_at else None
                    }
                    for note in item.notes.all()
                ]
            }

            # Add type-specific convenience fields for backwards compatibility
            if item.extraction_type == 'inspection_log':
                result['inspection_frequency'] = metadata.get('inspection_frequency')
            elif item.extraction_type == 'owner_deliverables_log':
                result['deliverable_type'] = metadata.get('deliverable_type')
            elif item.extraction_type == 'qa_planner':
                result['paragraph_number'] = item.paragraph_number

            # Expose shared metadata convenience fields
            result['when_due'] = metadata.get('when_due')

            results.append(result)

        return results
    
    def to_representation(self, instance):
        """Override to use filtered submittals from context."""
        data = super().to_representation(instance)
        
        # Use filtered submittals from context if available
        if 'filtered_submittals' in self.context:
            filtered_submittals = self.context['filtered_submittals']
            data['submittal_highlights'] = SubmittalHighlightSerializer(
                filtered_submittals, many=True, context=self.context
            ).data
        else:
            # Fallback to default submittalitem_set
            data['submittal_highlights'] = SubmittalHighlightSerializer(
                instance.submittalitem_set.all(), many=True, context=self.context
            ).data
        
        # Debug the final data structure
        print(f"🚀 FINAL API RESPONSE:")
        print(f"   - submittal_highlights count: {len(data.get('submittal_highlights', []))}")
        print(f"   - ai_log_highlights count: {len(data.get('ai_log_highlights', []))}")
        if data.get('ai_log_highlights'):
            print(f"   - ai_log_highlights sample: {data['ai_log_highlights'][0] if data['ai_log_highlights'] else 'None'}")
            
        return data


class SpecCentricViewSerializer(serializers.Serializer):
    """Main serializer for spec centric view data."""
    spec_sections = SpecSectionSerializer(many=True, read_only=True)
    total_sections = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(read_only=True)
    project_version_id = serializers.IntegerField(read_only=True, allow_null=True)
    
    def to_representation(self, instance):
        """Custom representation to include feature flag check."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            team = getattr(request, 'team', None)
            project = instance.get('project')
            
        
        return super().to_representation(instance)
