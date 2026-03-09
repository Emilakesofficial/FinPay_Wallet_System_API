"""
URL configuration for audit API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'audit'

router = DefaultRouter()
router.register(r'audit', views.AuditLogViewSet, basename='audit')

urlpatterns = [
    path('', include(router.urls)),
]