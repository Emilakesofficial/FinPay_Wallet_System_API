"""Common serializers for error response and utilities."""
from rest_framework import serializers

class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response format"""
    error = serializers.CharField(help_text="Error class name")
    code = serializers.CharField(help_text="Machine-readable error code")
    message = serializers.CharField(help_text="Human-readable error message")
    details = serializers.JSONField(help_text="Additional error context", required=False)
    status_code = serializers.IntegerField(help_text="HTTP status code")
    
class ValidationErrorSerializer(serializers.Serializer):
    """Validation error response"""
    error = serializers.CharField(default="ValidationError")
    code = serializers.CharField(default="ValidationError")
    message = serializers.CharField()
    details = serializers.DictField()
    status_code = serializers.IntegerField(default=400)