from rest_framework import serializers
from .models import Project

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'team', 'owner']

    def validate(self, data):
        owner = data.get('owner')
        team = data.get('team')
        
        if owner and team and not owner.is_member_of_team(team):
            raise serializers.ValidationError("The owner must be a member of the team.")
        
        return data
