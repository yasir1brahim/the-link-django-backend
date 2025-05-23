from rest_framework import serializers
from apps.deliverables.models import Chat

class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ['id', 'user', 'created_at']

