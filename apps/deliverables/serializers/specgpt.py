from rest_framework import serializers
from apps.deliverables.models import Chat, ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    sources = serializers.JSONField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'message', 'created_at', 'type', 'sources']



class ChatDetailSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ['id', 'user', 'created_at', 'messages']

    def get_messages(self, obj):
        return ChatMessageSerializer(obj.messages.order_by('created_at'), many=True).data




