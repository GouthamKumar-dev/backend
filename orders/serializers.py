# orders/serializers.py
from rest_framework import serializers
from .models import Order, OrderDetail, CartItem, Cart
from products.serializers import ProductSerializer

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
    order_details = OrderDetailSerializer(many=True, read_only=True)
    tracking_id = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ['order_id', 'user', 'total_price', 'shipping_address', 'status', 'tracking_id', 'created_at', 'order_details','is_active']


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
