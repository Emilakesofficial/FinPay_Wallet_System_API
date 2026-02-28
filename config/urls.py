from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]

# Customize admin site
admin.site.site_header = 'Wallet System Administration'
admin.site.site_title = 'Wallet System Admin'
admin.site.index_title = 'Welcome to Wallet System Administration'
