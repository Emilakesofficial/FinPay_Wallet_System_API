"""
URL configuration for wallet API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'wallets'

router = DefaultRouter()
router.register(r'wallets', views.WalletViewSet, basename='wallet')
router.register(r'transactions', views.TransactionViewSet, basename='transaction')

urlpatterns = [
    path('', include(router.urls)),
]