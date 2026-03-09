"""Serializers for Audit API"""
from rest_framework import serializers
from .models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for audit logs."""
    
    actor_email = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLog
        fields = [
            'id',
            'actor',
            'actor_email',
            'action',
            'target_type',
            'target_id',
            'changes',
            'ip_address',
            'user_agent',
            'metadata',
            'created_at',
        ]
        read_only_fields =  [
             'id',
            'actor',
            'actor_email',
            'action',
            'target_type',
            'target_id',
            'changes',
            'ip_address',
            'user_agent',
            'metadata',
            'created_at',
        ]
        
    def get_actor_email(self, obj) -> str | None:
        if obj.actor:
            return obj.actor.email
        return None
    
class AuditLogFilterSerializer(serializers.Serializer):
    """Serializer for audit log filters."""
    
    action = serializers.CharField(required=False)
    actor_id = serializers.UUIDField(required=False)
    target_type = serializers.CharField(required=False)
    target_id = serializers.UUIDField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
