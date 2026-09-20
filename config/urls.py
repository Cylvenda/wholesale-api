from django.contrib import admin
from django.urls import path, re_path, include
from drf_spectacular.views import (SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView, )
from django.conf.urls.static import static
from django.conf import settings
from config.api import dashboard_stats, export_report

urlpatterns = [
               path("admin/", admin.site.urls), re_path(r"^api/auth/", include("djoser.urls")),
               re_path(r"^api/auth/", include("djoser.urls.jwt")),
               path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
               # Swagger UI
               path("", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui", ),  # ReDoc
               path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc", ),

               # local apps routes
                path("api/", include("apps.accounts.urls")),
                path("api/", include("apps.customers.urls")),
                path("api/", include("apps.payments.urls")),
                path("api/", include("apps.products.urls")),
                path("api/", include("apps.purchases.urls")),
                path("api/", include("apps.sales.urls")),
                path("api/", include("apps.stock.urls")),
                path("api/", include("apps.suppliers.urls")),
                path("api/", include("apps.expenses.urls")),

                # Dashboard analytics
                path("api/dashboard/", dashboard_stats, name="dashboard-stats"),
                path("api/export/", export_report, name="export-report"),

                ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)