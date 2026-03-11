"""
API views for reconciliation.
"""
import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import ReconciliationReport, ReconciliationStatus, ReconciliationType
from .serializers import (
    ReconciliationReportSerializer,
    ReconciliationReportListSerializer,
    TriggerReconciliationSerializer,
    ReconciliationStatusSerializer,
    ReconciliationSummarySerializer,
)
from .tasks import run_reconciliation
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.db import connection
from config.celery import app as celery_app

logger = logging.getLogger(__name__)


class IsAdminUser(permissions.BasePermission):
    """Allow access only to admin users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


@extend_schema(tags=['Reconciliation'])
class ReconciliationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for reconciliation reports.
    Admin-only endpoints for viewing and triggering reconciliation.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    queryset = ReconciliationReport.objects.all().select_related('triggered_by')
    
    def get_serializer_class(self):
        """Return appropriate serializer."""
        if self.action == 'list':
            return ReconciliationReportListSerializer
        return ReconciliationReportSerializer
    
    @extend_schema(
        parameters=[
            OpenApiParameter(name='status', type=str, enum=[s[0] for s in ReconciliationStatus.choices]),
            OpenApiParameter(name='run_type', type=str, enum=[t[0] for t in ReconciliationType.choices]),
            OpenApiParameter(name='start_date', type=str),
            OpenApiParameter(name='end_date', type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        List reconciliation reports with optional filters.
        Query Parameters:
        - status: Filter by status (RUNNING, PASSED, WARNING, FAILED, CRITICAL)
        - run_type: Filter by run type (SCHEDULED, MANUAL, POST_TRANSACTION)
        - start_date: Filter reports after this date (ISO format)
        - end_date: Filter reports before this date (ISO format)
        """
        queryset = self.get_queryset()
        
        # Apply filters
        if status_filter := request.query_params.get('status'):
            queryset = queryset.filter(status=status_filter)
        
        if run_type := request.query_params.get('run_type'):
            queryset = queryset.filter(run_type=run_type)
        
        if start_date := request.query_params.get('start_date'):
            queryset = queryset.filter(started_at__gte=start_date)
        
        if end_date := request.query_params.get('end_date'):
            queryset = queryset.filter(started_at__lte=end_date)
        
        queryset = queryset.order_by('-started_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        request=TriggerReconciliationSerializer,
        responses={202: ReconciliationReportListSerializer}
    )
    @action(detail=False, methods=['post'])
    def trigger(self, request):
        """
        Trigger a new reconciliation run.
        This will queue a reconciliation task in Celery and return immediately.
        The reconciliation runs asynchronously in the background.
        """
        serializer = TriggerReconciliationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        run_type = serializer.validated_data.get('run_type', ReconciliationType.MANUAL)
        
        # Check if already running
        if ReconciliationReport.objects.filter(
            status=ReconciliationStatus.RUNNING
        ).exists():
            return Response(
                {'error': 'A reconciliation is already running'},
                status=status.HTTP_409_CONFLICT
            )
        
        report = ReconciliationReport.objects.create(
            run_type=run_type,
            status=ReconciliationStatus.RUNNING,
            triggered_by=request.user
        )
        
        try:
        # ✅ Create report immediately (no race condition)
            report = ReconciliationReport.objects.create(
                run_type=run_type,
                status=ReconciliationStatus.RUNNING,
                triggered_by=request.user
            )
            
            # ✅ Queue Celery task with report ID
            run_reconciliation.delay(str(report.id))

            logger.info(
                f"Reconciliation {report.id} triggered by {request.user.email}"
            )
            
            # Return report immediately
            response = ReconciliationReportSerializer(report)
            return Response(
                response.data,
                status=status.HTTP_202_ACCEPTED
            )
        except Exception as e:
            logger.error(f"Failed to trigger reconciliation: {e}")
            return Response(
                {'error': 'Failed to trigger reconciliation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @extend_schema(responses={200: ReconciliationStatusSerializer})
    @action(detail=False, methods=['get'])
    def status(self, request):
        """
        Get current reconciliation status and summary.
        Returns:
        - Whether a reconciliation is currently running
        - Latest report
        - Overall health summary
        """
        # Check if running
        is_running = ReconciliationReport.objects.filter(
            status=ReconciliationStatus.RUNNING
        ).exists()
        
        # Get latest report
        latest = ReconciliationReport.objects.order_by('-started_at').first()
        
        # Count reports
        total_reports = ReconciliationReport.objects.count()
        last_24h = ReconciliationReport.objects.filter(
            started_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        # Health summary (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        health_summary = ReconciliationReport.objects.filter(
            started_at__gte=seven_days_ago
        ).values('status').annotate(
            count=Count('id')
        )
        
        health_dict = {item['status']: item['count'] for item in health_summary}
        
        data = {
            'is_running': is_running,
            'latest_report': latest,
            'total_reports': total_reports,
            'last_24h_reports': last_24h,
            'health_summary': health_dict
        }
        
        serializer = ReconciliationStatusSerializer(instance=data)
        return Response(serializer.data)
    
    @extend_schema(responses={200: ReconciliationReportListSerializer})
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get the most recent reconciliation report."""
        latest = ReconciliationReport.objects.order_by('-started_at').first()
        
        if not latest:
            return Response(
                {'message': 'No reconciliation reports found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ReconciliationReportSerializer(latest)
        return Response(serializer.data)
    
    @extend_schema(responses={200: ReconciliationSummarySerializer})
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get reconciliation summary statistics.
        Returns aggregated statistics about reconciliation runs.
        """
        now = timezone.now()
        
        total = ReconciliationReport.objects.count()
        last_7d = ReconciliationReport.objects.filter(
            started_at__gte=now - timedelta(days=7)
        ).count()
        last_30d = ReconciliationReport.objects.filter(
            started_at__gte=now - timedelta(days=30)
        ).count()
        
        # Status breakdown
        status_breakdown = ReconciliationReport.objects.values('status').annotate(
            count=Count('id')
        )
        status_dict = {item['status']: item['count'] for item in status_breakdown}
        
        # Average duration
        avg_duration = ReconciliationReport.objects.filter(
            duration_seconds__isnull=False
        ).aggregate(avg=Avg('duration_seconds'))['avg'] or 0
        
        # Latest report
        latest = ReconciliationReport.objects.order_by('-started_at').first()
        
        # Recent failures (last 10)
        recent_failures = ReconciliationReport.objects.filter(
            status__in=[ReconciliationStatus.FAILED, ReconciliationStatus.CRITICAL]
        ).order_by('-started_at')[:10]
        
        failure_list = [
            {
                'id': str(r.id),
                'status': r.status,
                'started_at': r.started_at,
                'total_issues': r.total_issues
            }
            for r in recent_failures
        ]
        
        data = {
            'total_reports': total,
            'reports_last_7d': last_7d,
            'reports_last_30d': last_30d,
            'status_breakdown': status_dict,
            'average_duration': round(avg_duration, 2),
            'latest_report': latest,
            'recent_failures': failure_list
        }
        
        serializer = ReconciliationSummarySerializer(instance=data)
        return Response(serializer.data)
    
    @extend_schema(
        request=ReconciliationReportSerializer,
        responses={200: ReconciliationReportSerializer}
    )
    @action(detail=True, methods=['patch'])
    def add_notes(self, request, pk=None):
        """
        Add admin notes to a reconciliation report.
        Admins can add notes to document actions taken or observations.
        """
        report = self.get_object()
        
        notes = request.data.get('notes', '')
        if notes:
            if report.notes:
                report.notes += f"\n\n---\n{timezone.now().isoformat()} - {request.user.email}:\n{notes}"
            else:
                report.notes = f"{timezone.now().isoformat()} - {request.user.email}:\n{notes}"
            
            report.save(update_fields=['notes', 'updated_at'])
            logger.info(f"Notes added to report {report.id} by {request.user.email}")
        
        serializer = self.get_serializer(report)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def test_celery(self, request):
        """Test if Celery is working properly."""
        from config.celery import app
        
        results = {
            'broker_url': app.conf.broker_url[:50] + '...' if len(app.conf.broker_url) > 50 else app.conf.broker_url,
            'result_backend': app.conf.result_backend[:50] + '...' if app.conf.result_backend and len(app.conf.result_backend) > 50 else app.conf.result_backend,
        }
        
        # Test broker connection
        try:
            conn = app.connection()
            conn.ensure_connection(max_retries=3)
            conn.close()
            results['broker_connected'] = True
            results['broker_error'] = None
        except Exception as e:
            results['broker_connected'] = False
            results['broker_error'] = str(e)
        
        # Test sending a task
        try:
            from .tasks import check_global_balance
            
            # Create a dummy report for testing
            report = ReconciliationReport.objects.create(
                run_type='TEST',
                status=ReconciliationStatus.PENDING,
                triggered_by=request.user if request.user.is_authenticated else None,
                started_at=timezone.now()
            )
            
            task_result = check_global_balance.delay(str(report.id))
            results['task_sent'] = True
            results['task_id'] = str(task_result.id)
            results['test_report_id'] = str(report.id)
            results['task_error'] = None
        except Exception as e:
            results['task_sent'] = False
            results['task_id'] = None
            results['task_error'] = str(e)
        
        return Response(results)
    
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for monitoring.
    Checks:
    - Database connection
    - Redis/Celery broker connection
    - Celery worker status
    """
    health = {
        'status': 'healthy',
        'checks': {}
    }
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['checks']['database'] = f'error: {str(e)}'
        health['status'] = 'unhealthy'
    
    # Check Redis/Broker
    try:
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=3)
        conn.release()
        health['checks']['redis'] = 'ok'
    except Exception as e:
        health['checks']['redis'] = f'error: {str(e)}'
        health['status'] = 'unhealthy'
    
    # Check Celery workers
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            active_workers = len(stats)
            health['checks']['celery_workers'] = f'ok ({active_workers} active)'
        else:
            health['checks']['celery_workers'] = 'warning: no workers detected'
            health['status'] = 'degraded'
    except Exception as e:
        health['checks']['celery_workers'] = f'error: {str(e)}'
        health['status'] = 'unhealthy'
    
    status_code = 200 if health['status'] == 'healthy' else 503
    return Response(health, status=status_code)