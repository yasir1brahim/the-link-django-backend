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
        
    
    def get_ai_log_highlights(self, instance):
        """Extract AI log items with pdf_locations that match the current spec section."""
        ai_logs = self.context.get('ai_log_data', [])
        print(f"🔍 AI LOGS COUNT: {len(ai_logs)}")
        
        # Handle both dictionary and model instance formats
        if isinstance(instance, dict):
            # Instance is a dictionary with 'spec_section' key
            spec_section = instance.get('spec_section')
            spec_section_number = spec_section.masterformat_section.masterformat_number if spec_section and spec_section.masterformat_section else None
        else:
            # Instance is a model object
            spec_section_number = instance.masterformat_section.masterformat_number if instance.masterformat_section else None
        
        print(f"🎯 TARGET SPEC SECTION: {spec_section_number}")
        
        if not spec_section_number or not ai_logs:
            print(f"❌ EARLY RETURN: spec_section_number={spec_section_number}, ai_logs_count={len(ai_logs)}")
            return []
        
        # Filter log items that match this spec section and have pdf_locations
        matching_items = []
        for log in ai_logs:
            extraction_type = log.log_type
            item_data_rows = log.log_data or []
            print(f"📋 LOG TYPE: {extraction_type}, ITEMS COUNT: {len(item_data_rows)}")
            
            for item in item_data_rows:
                # Check if the item's spec section matches using fuzzy matching
                item_section = item.get('Spec Section #', item.get('spec_section_number', ''))
                has_pdf_locations = 'pdf_locations' in item
                print(f"📄 ITEM: section='{item_section}', has_pdf_locations={has_pdf_locations}")

                if self.fuzzy_match_spec_section_number(item_section, spec_section_number):
                    if has_pdf_locations:
                        print(f"✅ MATCH FOUND: Adding item with pdf_locations")
                        
                        # Get item_type and normalize it to code format (lowercase with underscores)
                        raw_item_type = item.get('item_type', '')
                        
                        matching_items.append({
                            'pdf_locations': item['pdf_locations'],
                            'spec_section_number': item_section,
                            'spec_section_name': item.get('Spec Section Name', item.get('spec_section_name', '')),
                            # Include relevant fields based on log type
                            'item_type': raw_item_type,
                            'extraction_type': extraction_type,
                            'requirement_text': item.get('Requirement Text', item.get('requirement_text', item.get('Inspection Type And Requirements', item.get('inspection_type_and_requirements', '')))),
                        })
                    else:
                        print(f"⚠️ MATCH BUT NO PDF_LOCATIONS: section matches but no pdf_locations field")
        
        print(f"🎉 FINAL MATCHING ITEMS COUNT: {len(matching_items)}")
        return matching_items
    
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
