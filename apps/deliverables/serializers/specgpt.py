from rest_framework import serializers
from apps.deliverables.models import Chat


class ChatMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()
    role = serializers.CharField()
    sources = serializers.SerializerMethodField()

    def get_sources(self, obj):
        return obj.sources


class ChatDetailSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ['id', 'user', 'created_at', 'messages']

    def get_messages(self, obj):
        return ChatMessageSerializer(obj.messages, many=True).data



