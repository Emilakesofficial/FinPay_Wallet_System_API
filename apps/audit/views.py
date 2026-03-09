"""
Admin-only audit API views.
"""
import logging
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import AuditLog, AuditAction
from .serializers import AuditLogSerializer

logger = logging.getLogger(__name__)


class IsAdminUser(permissions.BasePermission):
    """Allow access only to admin users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_staff


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin-only viewset for audit logs.
    Endpoints:
    - GET /audit/ - List audit logs (with filters)
    - GET /audit/{id}/ - Get audit log detail
    - GET /audit/summary/ - Get audit summary stats
    """
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        """Return filtered audit logs."""
        queryset = AuditLog.objects.select_related('actor').order_by('-created_at')
        
        # Filter by action
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by actor
        actor_id = self.request.query_params.get('actor_id')
        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)
        
        # Filter by target
        target_type = self.request.query_params.get('target_type')
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        
        target_id = self.request.query_params.get('target_id')
        if target_id:
            queryset = queryset.filter(target_id=target_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset
    
    @extend_schema(
        parameters=[
            OpenApiParameter(name='action', type=str, enum=[c[0] for c in AuditAction.choices]),
            OpenApiParameter(name='actor_id', type=str),
            OpenApiParameter(name='target_type', type=str),
            OpenApiParameter(name='target_id', type=str),
            OpenApiParameter(name='start_date', type=str),
            OpenApiParameter(name='end_date', type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        """List audit logs with optional filters."""
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get audit summary statistics."""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Actions in last 24 hours
        recent_actions = AuditLog.objects.filter(
            created_at__gte=last_24h
        ).values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Actions in last 7 days by day
        daily_stats = AuditLog.objects.filter(
            created_at__gte=last_7d
        ).extra(
            select={'date': 'DATE(created_at)'}
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Top actors
        top_actors = AuditLog.objects.filter(
            created_at__gte=last_7d,
            actor__isnull=False
        ).values(
            'actor__email'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        return Response({
            'last_24h_by_action': list(recent_actions),
            'last_7d_by_day': list(daily_stats),
            'top_actors_7d': list(top_actors),
            'total_logs': AuditLog.objects.count(),
        })
    
    @action(detail=False, methods=['get'])
    def actions(self, request):
        """List available audit actions."""
        return Response({
            'actions': [
                {'value': choice[0], 'label': choice[1]}
                for choice in AuditAction.choices
            ]
        })