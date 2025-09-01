from rest_framework import serializers
from apps.deliverables.models import Chat, ChatMessage, AiGeneratedLog
from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active


class ChatMessageSerializer(serializers.ModelSerializer):
    sources = serializers.JSONField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'message', 'created_at', 'type', 'sources']


class ChatDetailSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ['id', 'project', 'project_version', 'user', 'created_at', 'messages']

    def get_messages(self, obj):
        messages = obj.messages.all().order_by('created_at')
        return ChatMessageSerializer(messages, many=True).data


class AiGeneratedLogSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_version_number = serializers.CharField(source='project_version.version_number', read_only=True)
    log_data = serializers.JSONField(required=False, allow_null=True)
    data_format = serializers.SerializerMethodField()
    
    class Meta:
        model = AiGeneratedLog
        fields = [
            'id', 'project', 'project_version', 'log_type', 'log_status', 
            'log_table', 'log_data', 'data_format', 'created_at', 'project_name', 'project_version_number'
        ]
        read_only_fields = ['id', 'created_at', 'project_name', 'project_version_number', 'data_format']
    
    def get_data_format(self, obj):
        """Return appropriate data format based on feature flag status."""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return 'markdown'  # Default to markdown if no request context
        
        try:
            # Get user, team, and project from request context
            user = request.user
            team = getattr(request, 'team', None)
            project = obj.project
            
            # Check if feature flag is active
            use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(user, team, project)
            
            # Return structured format if flag is active and structured data is available
            if use_data_tables and obj.log_data:
                return 'structured'
            else:
                return 'markdown'
        except Exception as e:
            # Log error and default to markdown for safety
            print(f"Error determining data format for log {obj.id}: {str(e)}")
            return 'markdown'
    
    def to_representation(self, instance):
        """
        Override to_representation to apply sorting to structured data.
        """
        data = super().to_representation(instance)
        
        # Apply sorting to log_data if it exists and sorting parameters are provided
        request = self.context.get('request')
        if data.get('log_data') and request and hasattr(request, 'sort_field'):
            sort_field = getattr(request, 'sort_field', None)
            sort_direction = getattr(request, 'sort_direction', 'desc')
            
            if sort_field and sort_field != 'created_at':
                data['log_data'] = self.sort_structured_data(data['log_data'], sort_field, sort_direction)
        
        return data
    
    def sort_structured_data(self, log_data, sort_field, sort_direction):
        """
        Sort structured data by the specified field and direction.
        """
        try:
            # Map field names to the actual keys in the structured data
            field_mapping = {
                'spec_section_number': 'Spec Section #',
                'spec_section_name': 'Spec Section Name',
                'inspection_type_and_requirements': 'Inspection Type And Requirements',
                'inspection_frequency': 'Inspection Frequency',
                'responsible_party': 'Responsible Party',
                'deliverable_type': 'Deliverable Type',
                'when_due': 'When Due',
                'exact_requirement_text': 'Exact Requirement Text'
            }
            
            # Get the actual field key
            field_key = field_mapping.get(sort_field, sort_field)
            
            # Sort the data
            reverse = sort_direction == 'desc'
            
            # Handle None values by placing them at the end
            def sort_key(item):
                value = item.get(field_key, '')
                if value is None:
                    return '' if reverse else 'zzz'  # Place None at end for desc, beginning for asc
                return str(value).lower()
            
            sorted_data = sorted(log_data, key=sort_key, reverse=reverse)
            
            return sorted_data
            
        except Exception as e:
            # Log error and return original data
            print(f"Error sorting structured data: {str(e)}")
            return log_data




