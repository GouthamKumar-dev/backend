# ecommerce/urls.py
from django.urls import path, include
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf import settings
from django.conf.urls.static import static
from .views import landing_page,send_query_email,terms_and_conditions,privacy_policy,cancellation_and_refunds,shipping_policy

# drf-yasg Schema View Configuration
schema_view = get_schema_view(
    openapi.Info(
        title="E-Commerce API",
        default_version='v1',
        description="API documentation for the E-Commerce platform",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="support@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(AllowAny,),
)

urlpatterns = [
    # Admin Panel
    path('', landing_page, name='landing_page'),
    path('send-query-email/', send_query_email, name='send_query_email'),
    path('terms-and-conditions/', terms_and_conditions, name='terms_and_conditions'),
    path('privacy-policy/', privacy_policy, name='privacy_policy'),
    path('cancellation-and-refunds/', cancellation_and_refunds, name='cancellation_and_refunds'),
    path('shipping-policy/', shipping_policy, name='shipping_policy'),

    # App-specific URLs
    path('api/users/', include('users.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/', include('orders.urls')),

    # Swagger UI and ReDoc Endpoints
    path('api/docs/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/docs/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/schema/', schema_view.without_ui(cache_timeout=0), name='schema-json')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
