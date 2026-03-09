"""
URL configuration for reconciliation API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'reconciliation'

router = DefaultRouter()
router.register(r'reconciliation/reports', views.ReconciliationViewSet, basename='reconciliation')

urlpatterns = [
    path('', include(router.urls)),
]