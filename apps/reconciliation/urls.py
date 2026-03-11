"""
URL configuration for reconciliation API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import health_check

app_name = 'reconciliation'

router = DefaultRouter()
router.register(r'reconciliation/reports', views.ReconciliationViewSet, basename='reconciliation')

urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health-check')
]