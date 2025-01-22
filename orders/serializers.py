from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderDetail
from products.serializers import ProductSerializer
from users.serializers import UserSerializer

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = CartItem
        fields = ['product', 'quantity']

class CartSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    products = CartItemSerializer(source='cartitem_set', many=True)

    class Meta:
        model = Cart
        fields = ['cart_id', 'user', 'products']

class OrderDetailSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = OrderDetail
        fields = ['product', 'quantity', 'price_at_purchase']

class OrderSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    order_details = OrderDetailSerializer(many=True)

    class Meta:
        model = Order
        fields = ['order_id', 'user', 'created_at', 'updated_at', 'status', 'order_details']