# views.py
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Order, OrderDetail, Cart, CartItem
from products.models import Product
from .serializers import CartItemSerializer, OrderSerializer, CartSerializer, OrderDetailSerializer

from rest_framework.pagination import PageNumberPagination

class CartItemPagination(PageNumberPagination):
    page_size = 5  # Number of cart items per page
    page_size_query_param = 'page_size'
    max_page_size = 20

class CartViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer
    pagination_class = CartItemPagination  # Apply pagination
    http_method_names = ['get', 'post','put', 'delete']

    def get_queryset(self):
        """
        Return the cart with only active cart items for the user.
        """
        cart = Cart.objects.filter(user=self.request.user).first()
        
        if not cart:
            return Cart.objects.none()

        # Ensure that only active cart items are included
        cart.cartitem_set.filter(is_active=True)

        return Cart.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        """
        Return a specific CartItem by its primary key (`pk`).
        """
        cart_item = CartItem.objects.filter(id=kwargs['pk'], cart__user=request.user).first()
        
        if not cart_item:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Return the CartItem data serialized using CartItemSerializer
        return Response(CartItemSerializer(cart_item).data)

    def create(self, request, *args, **kwargs):
        """ Create cart and add items """
        user = request.user
        products = request.data.get("products", [])

        # Create Cart for the user if it doesn't exist
        cart, created = Cart.objects.get_or_create(user=user)

        # Create CartItems
        for product_data in products:
            product_id = product_data.get("product")  # Make sure you're using "product" as the field name
            quantity = product_data.get("quantity", 1)

            # Ensure the product exists
            try:
                product = Product.objects.get(product_id=product_id)  # Fetch the product by ID
            except Product.DoesNotExist:
                return Response({"error": "Product not found"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if product already exists in the cart and update the quantity if it does
            cart_item = CartItem.objects.filter(cart=cart, product=product, is_active=True).first()
            if cart_item:
                # If the product is already in the cart, update the quantity
                cart_item.quantity += quantity  # Increase the quantity
                cart_item.save()
            else:
                # Create a new CartItem if it doesn't exist
                CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=quantity,
                    is_active=True
                )

        # Return updated cart data
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Update the cart item details (e.g., change quantity).
        """
        # Retrieve the CartItem using the pk provided in the URL
        cart_item = CartItem.objects.filter(id=kwargs['pk'], cart__user=request.user).first()

        if not cart_item:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the new quantity from the request data
        quantity = request.data.get("quantity", None)

        if quantity is None:
            return Response({"error": "Quantity is required"}, status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response({"error": "Quantity must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        # Update the quantity
        cart_item.quantity = quantity
        cart_item.save()

        # Return the updated CartItem serialized data
        return Response(CartItemSerializer(cart_item).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete a cart item by setting is_active=False.
        """
        # Retrieve the CartItem using the pk provided in the URL
        cart_item = CartItem.objects.filter(id=kwargs['pk'], cart__user=request.user).first()

        if not cart_item:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Set the is_active flag to False for soft delete
        cart_item.is_active = False
        cart_item.save()

        # Return success response
        return Response({"message": "Cart item marked as inactive"}, status=status.HTTP_204_NO_CONTENT)


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ['get', 'post', 'put']

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user, is_active=True).order_by('-created_at')

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        order_details = order.order_details.filter(is_active=True)

        return Response({
            "order_id": order.order_id,
            "total_price": order.total_price,
            "status": order.status,
            "shipping_address": order.shipping_address,
            # "products": OrderSerializer(order).data,  # Order-level details
            "items": OrderDetailSerializer(order_details, many=True).data  # All product details without pagination
        })

    @transaction.atomic
    def create(self, request):
        """Create an order and put stock on hold by reducing stock temporarily."""
        user = request.user
        cart = Cart.objects.filter(user=user).first()

        # Check if cart exists and has active items
        cart_items = CartItem.objects.filter(cart=cart, is_active=True)
        if not cart or not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        shipping_address = request.data.get("shipping_address")
        if not shipping_address:
            return Response({"error": "Shipping address is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate total price
        total_price = sum(item.product.price * item.quantity for item in cart_items)

        # Create Order
        order = Order.objects.create(
            user=user,
            total_price=total_price,
            shipping_address=shipping_address,
            status="Pending"
        )

        # Move Cart Items to OrderDetail & Reduce Stock
        for item in cart_items:
            product = item.product
            
            # Check if enough stock is available
            if product.stock < item.quantity:
                return Response({"error": f"Not enough stock for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Reduce stock temporarily (on hold)
            product.stock -= item.quantity
            product.save()

            OrderDetail.objects.create(
                order=order,
                product=product,
                quantity=item.quantity,
                price_at_purchase=product.price
            )
            
            item.is_active = False  # Soft delete cart item
            item.save()

        # Empty the cart after placing the order
        cart_items.update(is_active=False)  # This will mark all cart items as inactive

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):

        order = self.get_object()
        new_status = request.data.get("status")

        if not order.is_active:
            return Response({"error": "Cannot update an inactive order"}, status=status.HTTP_400_BAD_REQUEST)

        if new_status == "Cancelled":
            order.is_active = False  # Soft delete order

            # Restore stock when order is canceled
            for item in order.order_details.all():
                product = item.product
                product.stock += item.quantity  # Return stock to inventory
                product.save()

        elif new_status in ["Processing", "Shipped", "Delivered"]:
            order.status = new_status
        else:
            return Response({"error": "Invalid status update"}, status=status.HTTP_400_BAD_REQUEST)

        order.save()
        return Response(OrderSerializer(order).data)

