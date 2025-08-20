from rest_framework import serializers
from apps.deliverables.models import Chat, ChatMessage, AiGeneratedLog


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
    
    class Meta:
        model = AiGeneratedLog
        fields = [
            'id', 'project', 'project_version', 'log_type', 'log_status', 
            'log_table', 'created_at', 'project_name', 'project_version_number'
        ]
        read_only_fields = ['id', 'created_at', 'project_name', 'project_version_number']




