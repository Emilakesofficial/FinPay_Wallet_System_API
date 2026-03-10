from django.urls import path
from .views import run_setup

urlpatterns = [
    path('', run_setup, name='run_setup'),
]