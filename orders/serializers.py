# orders/serializers.py
from rest_framework import serializers
from .models import Order, OrderDetail, CartItem, Cart
from products.serializers import ProductSerializer
from users.serializers import UserSerializer

# serializers.py

class OrderDetailSerializer(serializers.ModelSerializer):
    product_details = serializers.SerializerMethodField()

    class Meta:
        model = OrderDetail
        fields = ['order_detail_id', 'order', 'product', 'product_details', 'quantity', 'price_at_purchase', 'is_active']

    def get_product_details(self, obj):
        request = self.context.get('request')
        return ProductSerializer(obj.product, context={'request': request}).data


class OrderSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True) 
    order_details = OrderDetailSerializer(many=True, read_only=True)
    tracking_id = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ['order_id', 'user', 'total_price', 'shipping_address', 'status', 'tracking_id', 'created_at', 'order_details','is_active','updated_at']

    def get_order_details(self, obj):
        active_order_details = obj.order_details.filter(is_active=True)  # Filter only active details
        request = self.context.get('request')
        return OrderDetailSerializer(active_order_details, many=True, context={'request': request}).data


class CartItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    product_details = serializers.SerializerMethodField()  # Pass request to ProductSerializer

    class Meta:
        model = CartItem
        fields = ['id', 'product_details', 'quantity', 'is_active']

    def get_product_details(self, obj):
        request = self.context.get('request')  # Get request from parent serializer
        return ProductSerializer(obj.product, context={'request': request}).data




# Main Cart Serializer
class CartSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    products = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['cart_id', 'user', 'products']

    def get_products(self, obj):
        active_cart_items = obj.cartitem_set.filter(is_active=True)
        request = self.context.get('request')  # Retrieve request from context
        return CartItemSerializer(active_cart_items, many=True, context={'request': request}).data


# ========== NEW: SETTLEMENT & DELIVERY SERIALIZERS ==========
from .models import PaymentSettlement, DeliveryPartner, OrderLocationHistory

class PaymentSettlementSerializer(serializers.ModelSerializer):
    order_details = OrderSerializer(source='order', read_only=True)
    admin_details = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentSettlement
        fields = [
            'settlement_id', 'order', 'order_details', 'admin', 'admin_details',
            'amount', 'transaction_id', 'status', 'settlement_date'
        ]
        read_only_fields = ['settlement_id', 'settlement_date']
    
    def get_admin_details(self, obj):
        from users.serializers import UserSerializer
        return UserSerializer(obj.admin).data if obj.admin else None


class DeliveryPartnerSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    current_order_count = serializers.SerializerMethodField()
    
    class Meta:
        model = DeliveryPartner
        fields = [
            'partner_id', 'user', 'user_details', 'partner_name', 'phone_number',
            'vehicle_type', 'vehicle_number', 'current_lat', 'current_lng',
            'last_location_update', 'status', 'is_active', 'average_rating',
            'total_deliveries', 'current_order_count', 'joined_at', 'updated_at'
        ]
        read_only_fields = ['partner_id', 'average_rating', 'total_deliveries', 'joined_at']
    
    def get_current_order_count(self, obj):
        return obj.orders.filter(status__in=['Processing', 'Shipped']).count()


class OrderLocationHistorySerializer(serializers.ModelSerializer):
    delivery_partner_details = DeliveryPartnerSerializer(source='delivery_partner', read_only=True)
    
    class Meta:
        model = OrderLocationHistory
        fields = [
            'history_id', 'order', 'delivery_partner', 'delivery_partner_details',
            'latitude', 'longitude', 'status_at_location', 'notes', 'recorded_at'
        ]
        read_only_fields = ['history_id', 'recorded_at']


class OrderLocationUpdateSerializer(serializers.Serializer):
    """Serializer for updating order location from mobile app"""
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    status_at_location = serializers.CharField(max_length=50, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class OrderTrackingSerializer(serializers.ModelSerializer):
    """Enhanced order serializer with tracking information"""
    user = UserSerializer(read_only=True)
    order_details = OrderDetailSerializer(many=True, read_only=True)
    delivery_partner_details = DeliveryPartnerSerializer(source='delivery_partner', read_only=True)
    location_history = OrderLocationHistorySerializer(many=True, read_only=True)
    vendor_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'order_id', 'user', 'total_price', 'shipping_address', 'status', 
            'tracking_id', 'created_at', 'order_details', 'is_active', 'updated_at',
            'vendor', 'vendor_details', 'commission_amount', 'vendor_settlement_amount',
            'settlement_status', 'razorpay_transfer_id', 'settled_at',
            'delivery_partner', 'delivery_partner_details', 'current_location_lat',
            'current_location_lng', 'estimated_delivery_time', 'location_history'
        ]
    
    def get_vendor_details(self, obj):
        if obj.vendor:
            from users.serializers import VendorAccountSerializer
            return VendorAccountSerializer(obj.vendor).data
        return None
