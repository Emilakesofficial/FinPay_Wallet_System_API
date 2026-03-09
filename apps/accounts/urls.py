"""
URL configuration for authentication endpoints.
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication with JWT
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/token/refresh/', views.TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/me/', views.CurrentUserView.as_view(), name='current-user'),
    
    # Profile management
    path('auth/profile/', views.ProfileView.as_view(), name='profile'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
]