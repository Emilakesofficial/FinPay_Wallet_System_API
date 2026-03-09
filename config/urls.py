from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import(
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Swagger UI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # ReDoc
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    path("admin/", admin.site.urls),
    path('api/v1/', include('apps.accounts.urls')),
    path("api/v1/", include("apps.wallets.urls")),
    path("api/v1/", include("apps.audit.urls")),
    path("api/v1/", include("apps.reconciliation.urls")),
     
]
# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# Customize admin site
admin.site.site_header = 'Wallet System Administration'
admin.site.site_title = 'Wallet System Admin'
admin.site.index_title = 'Welcome to Wallet System Administration'
