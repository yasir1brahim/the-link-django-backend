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




