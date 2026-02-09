from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CartViewSet, OrderViewSet, UserOrdersViewSet, payment_webhook, razorpay_webhook, all_orders,
    # NEW: Settlement management views
    initiate_settlement, get_settlement_history, retry_settlement,
    auto_settle_all, get_vendor_settlement_summary, reverse_settlement,
    # NEW: Phase 4 - Real-time tracking views
    update_delivery_location, get_order_tracking, get_delivery_route,
    assign_delivery_partner, get_nearby_partners, get_delivery_partner_orders
)

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'order', OrderViewSet, basename='order')

urlpatterns = [
    path("", include(router.urls)),  
    path("all/", all_orders, name="all_orders"),
    path('users/<int:pk>/', UserOrdersViewSet.as_view({'get': 'user_orders'}), name='user-orders-detail'),
    path("payment-webhook/", payment_webhook, name="payment_webhook"),
    path("razorpay-webhook/", razorpay_webhook, name="razorpay_webhook"),  # NEW: POST webhook endpoint
    
    # ========== NEW: SETTLEMENT MANAGEMENT ==========
    path('settlements/initiate/<int:order_id>/', initiate_settlement, name='initiate_settlement'),
    path('settlements/', get_settlement_history, name='settlement_history'),
    path('settlements/<int:settlement_id>/retry/', retry_settlement, name='retry_settlement'),
    path('settlements/<int:settlement_id>/reverse/', reverse_settlement, name='reverse_settlement'),
    path('settlements/auto-settle/', auto_settle_all, name='auto_settle_all'),
    path('settlements/summary/', get_vendor_settlement_summary, name='vendor_settlement_summary'),
    path('settlements/summary/<int:vendor_id>/', get_vendor_settlement_summary, name='vendor_settlement_summary_by_id'),
    
    # ========== NEW: PHASE 4 - REAL-TIME ORDER TRACKING ==========
    path('order/<int:order_id>/location/update/', update_delivery_location, name='update_delivery_location'),
    path('order/<int:order_id>/tracking/', get_order_tracking, name='get_order_tracking'),
    path('order/<int:order_id>/route/', get_delivery_route, name='get_delivery_route'),
    path('order/<int:order_id>/assign-partner/', assign_delivery_partner, name='assign_delivery_partner'),
    path('delivery-partners/nearby/', get_nearby_partners, name='get_nearby_partners'),
    path('delivery-partner/orders/', get_delivery_partner_orders, name='get_delivery_partner_orders'),
]
