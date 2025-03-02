# views.py
from django.db import transaction
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Order, OrderDetail, Cart, CartItem
from products.models import Product
from .serializers import CartItemSerializer, OrderSerializer, CartSerializer, OrderDetailSerializer
from rest_framework.decorators import action, permission_classes, api_view
from users.permissions import IsAdminOrStaff,IsAdminUser
from users.serializers import UserSerializer
from django.shortcuts import get_object_or_404
from users.models import CustomUser

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

        # Ensure only active cart items are included
        cart_items = cart.cartitem_set.filter(is_active=True)

        # Attach request context to each cart item
        for item in cart_items:
            item.request = self.request

        return Cart.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """
        List the user's cart with active items and product images.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """
        Return a specific CartItem by its primary key (`pk`).
        """
        cart_item = CartItem.objects.filter(id=kwargs['pk'], cart__user=request.user).first()
        
        if not cart_item:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Return the CartItem data serialized using CartItemSerializer
        return Response(CartItemSerializer(cart_item,context={'request': request}).data)

    def create(self, request, *args, **kwargs):
        """ Create cart and add items """
        user = request.user
        products = request.data.get("products", [])

        # Create Cart for the user if it doesn't exist
        cart, created = Cart.objects.get_or_create(user=user)

        for product_data in products:
            product_id = product_data.get("product")  
            quantity = product_data.get("quantity", 1)

            # Ensure the product exists
            try:
                product = Product.objects.get(product_id=product_id, is_active = True)  
            except Product.DoesNotExist:
                return Response({"error": "Product not found"}, status=status.HTTP_400_BAD_REQUEST)

            # Validate stock before adding
            if quantity > product.stock:
                return Response({"error": f"Only {product.stock} available for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if item exists in cart
            existing_cart_item = CartItem.objects.filter(cart=cart, product=product).first()

            if existing_cart_item:
                if existing_cart_item.is_active:
                    return Response({
                        "error": f"{product.name} is already in the cart",
                        "cart_item_id": existing_cart_item.id  # Provide cart item ID
                    }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    # Reactivate and update quantity
                    existing_cart_item.quantity = quantity
                    existing_cart_item.is_active = True
                    existing_cart_item.save()
            else:
                # Create new cart item
                CartItem.objects.create(cart=cart, product=product, quantity=quantity, is_active=True)

        return Response(CartSerializer(cart,context={'request': request}).data, status=status.HTTP_201_CREATED)



    def update(self, request, *args, **kwargs):
        """
        Update cart item quantity.
        If quantity is set to 0, soft delete the cart item.
        """
        cart_item = CartItem.objects.filter(id=kwargs['pk'], cart__user=request.user).first()

        if not cart_item:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        quantity = request.data.get("quantity", None)

        if quantity is None:
            return Response({"error": "Quantity is required"}, status=status.HTTP_400_BAD_REQUEST)

        if quantity == 0:
            # Soft delete the item instead of updating
            cart_item.is_active = False
            cart_item.save()
            return Response({"message": "Cart item marked as inactive"}, status=status.HTTP_200_OK)

        # Check if requested quantity exceeds stock
        if quantity > cart_item.product.stock:
            return Response(
                {"error": f"Only {cart_item.product.stock} items available for {cart_item.product.name}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_item.quantity = quantity
        cart_item.save()

        return Response(CartItemSerializer(cart_item,context={'request': request}).data, status=status.HTTP_200_OK)

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
            "items": OrderDetailSerializer(order_details,context={'request': request}, many=True).data  # All product details without pagination
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

        return Response(OrderSerializer(order,context={'request': request}).data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        """Allow only staff/admin to update order status."""
        self.permission_classes = [IsAdminOrStaff]  # Only admins/staff can update
        self.check_permissions(request)  # Enforce the permission

        order = self.get_object()
        new_status = request.data.get("status")

        if not order.is_active:
            return Response({"error": "Cannot update an inactive order"}, status=status.HTTP_400_BAD_REQUEST)

        # ❌ Prevent updates if order is already delivered
        if order.status == "Delivered":
            return Response({"error": "This order has already been delivered and cannot be updated"}, status=status.HTTP_400_BAD_REQUEST)

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
        return Response(OrderSerializer(order,context={'request': request}).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminOrStaff])
def all_orders(request):
    """ 
    Admin/Staff can view all orders 
    """
    orders = Order.objects.filter(is_active=True).order_by("-created_at")
    serializer = OrderSerializer(orders, many=True, context={"request": request})
    return Response(serializer.data)
    
class UserOrdersViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    pagination_class = CartItemPagination  # Apply pagination

    @action(detail=True, methods=['get'], url_path='orders')
    def user_orders(self, request, pk=None):
        """
        Fetch all orders for a specific user.
        """
        user = get_object_or_404(CustomUser, pk=pk)
        orders = Order.objects.filter(user=user).order_by('-created_at')

        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


