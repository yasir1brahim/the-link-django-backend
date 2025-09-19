from rest_framework import serializers
from ..models import (
    SpecSection,
    SubmittalItem,
    MasterFormatSection,
    Project,
    ProjectVersion,
    UploadedFile
)
from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active


class SpecSectionSerializer(serializers.ModelSerializer):
    """Serializer for spec sections with basic information."""
    masterformat_number = serializers.CharField(source='masterformat_section.masterformat_number', read_only=True)
    masterformat_title = serializers.CharField(source='masterformat_section.title', read_only=True)
    document_name = serializers.CharField(source='document.name', read_only=True)
    document_id = serializers.IntegerField(source='document.id', read_only=True)
    
    class Meta:
        model = SpecSection
        fields = [
            'id',
            'masterformat_number',
            'masterformat_title',
            'custom_section_title',
            'document_name',
            'document_id',
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
    """Serializer for spec section content with submittal highlights."""
    spec_section = SpecSectionSerializer(read_only=True)
    content = serializers.CharField(read_only=True)
    submittal_highlights = SubmittalHighlightSerializer(many=True, read_only=True)
    
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
            
            # Check if feature flag is active
            if not is_spec_centered_view_feature_flag_active(user, team, project):
                return {'error': 'Spec centered view feature is not enabled for this user/team/project'}
        
        return super().to_representation(instance)
