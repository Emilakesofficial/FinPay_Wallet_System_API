from django.urls import path
from .views import run_setup

urlpattern = [
    path('', run_setup),
]