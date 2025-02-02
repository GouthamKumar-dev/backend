# orders/serializers.py
from rest_framework import serializers
from .models import Order, OrderDetail, CartItem, Cart
from products.serializers import ProductSerializer

# serializers.py

class OrderDetailSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)  # Full product details

    class Meta:
        model = OrderDetail
        fields = ['order_detail_id', 'order', 'product', 'product_details', 'quantity', 'price_at_purchase','is_active']


class OrderSerializer(serializers.ModelSerializer):
    order_details = OrderDetailSerializer(many=True, read_only=True)
    tracking_id = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ['order_id', 'user', 'total_price', 'shipping_address', 'status', 'tracking_id', 'created_at', 'order_details','is_active']


class CartItemSerializer(serializers.ModelSerializer):
    # Serialize the related product details
    product_details = ProductSerializer(source='product', read_only=True)  # Full product details

    class Meta:
        model = CartItem  # Ensure that this references the correct model
        fields = ['product', 'product_details', 'quantity', 'is_active']  # Include quantity and is_active



# Main Cart Serializer
class CartSerializer(serializers.ModelSerializer):
    # Represent the user as a string (username)
    user = serializers.StringRelatedField()

    # Use the CartItemSerializer to fetch items in the cart
    products = serializers.SerializerMethodField()  # Related CartItems (cartitem_set is default)

    class Meta:
        model = Cart  # Ensure that this references the correct model
        fields = ['cart_id', 'user', 'products']

    def get_products(self, obj):
        active_cart_items = obj.cartitem_set.filter(is_active=True)
        return CartItemSerializer(active_cart_items, many=True).data  # Serialize only active items
