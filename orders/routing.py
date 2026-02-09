"""
WebSocket URL Routing
"""

from django.urls import re_path
from orders import consumers

websocket_urlpatterns = [
    re_path(r'ws/tracking/order/(?P<order_id>\d+)/$', consumers.OrderTrackingConsumer.as_asgi()),
    re_path(r'ws/delivery-partner/dashboard/$', consumers.DeliveryPartnerTrackingConsumer.as_asgi()),
]
