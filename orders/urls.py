from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CartViewSet, OrderViewSet, UserOrdersViewSet, all_orders

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'order', OrderViewSet, basename='order')

urlpatterns = [
    path("", include(router.urls)),  
    path("all/", all_orders, name="all_orders"),
    path('users/<int:pk>/', UserOrdersViewSet.as_view({'get': 'user_orders'}), name='user-orders-detail'),
]
