# views.py
from django.db import transaction
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Order, OrderDetail, Cart, CartItem
from products.models import Product
from .serializers import CartItemSerializer, OrderSerializer, CartSerializer, OrderDetailSerializer
from rest_framework.decorators import action, permission_classes, api_view
from users.permissions import IsAdminOrStaff,IsAdminUser
from users.serializers import UserSerializer
from django.shortcuts import get_object_or_404
from users.models import CustomUser
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import hmac
import hashlib
import json
from ecommerce.logger import logger
from django.db.models import F
from django.core.mail import send_mail

from rest_framework.pagination import PageNumberPagination

from razorpay.errors import BadRequestError, ServerError
import razorpay
from django.core.mail import send_mail

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
                        "cart_item_id": existing_cart_item.id
                    }, status=status.HTTP_400_BAD_REQUEST)
                elif quantity > product.stock:
                    return Response({"error": f"Only {product.stock} available for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)
                else:
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
    http_method_names = ["get", "post", "put"]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user, is_active=True).order_by("-created_at")

    @transaction.atomic
    def create(self, request):
        """Create an order and generate a Razorpay Payment Link."""
        user = request.user
        cart = Cart.objects.filter(user=user).first()
        cart_items = CartItem.objects.filter(cart=cart, is_active=True)

        if not cart or not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        shipping_address = request.data.get("shipping_address")
        if not shipping_address:
            return Response({"error": "Shipping address is required"}, status=status.HTTP_400_BAD_REQUEST)

        total_price =sum(item.product.offer_price * item.quantity for item in cart_items)
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            # Create order in the database but keep it pending
            order = Order.objects.create(
                user=user,
                total_price=total_price,
                shipping_address=shipping_address,
                status="Pending"
            )

            # Move Cart Items to OrderDetail (without modifying stock)
            for item in cart_items:
                OrderDetail.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price_at_purchase=item.product.offer_price
                )

            # Create a Razorpay Payment Link
            payment_link = client.payment_link.create({
                "amount": int(total_price * 100),  # Convert to paise
                "currency": "INR",
                "description": f"Order #{order.order_id} Payment",
                "customer": {
                    "name": user.username,
                    "email": user.email,
                    "contact": user.phone_number,  # Ensure phone number is available
                },
                "callback_url": "https://tstocks.in/api/orders/payment-webhook/",
                "callback_method": "get"
            })

            # Save Razorpay payment link ID
            order.razorpay_payment_link_id = payment_link["id"]
            order.save()

            return Response({
                "order_id": order.order_id,
                "payment_link": payment_link["short_url"]
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"])
    def verify(self, request):
        """Verify payment and update order status"""
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_payment_link_id = request.data.get("razorpay_payment_link_id")

        order = Order.objects.filter(razorpay_payment_link_id=razorpay_payment_link_id, is_active=True).first()
        if not order:
            return Response({"error": "Order not found or inactive"}, status=status.HTTP_404_NOT_FOUND)

        try:
            payment = client.payment.fetch(razorpay_payment_id)

            if payment["status"] == "captured":
                order.status = "Processing"
                order.razorpay_payment_id = razorpay_payment_id
                order.save()
                return Response({"message": "Payment verified successfully"}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Payment not completed"}, status=status.HTTP_400_BAD_REQUEST)

        except razorpay.errors.BadRequestError:
            return Response({"error": "Invalid payment details"}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        order_details = order.order_details.filter(is_active=True)

        return Response({
            "order_id": order.order_id,
            "total_price":  sum(detail.product.get_offer_price() * detail.quantity for detail in  order_details),
            "status": order.status,
            "shipping_address": order.shipping_address,
            "items": OrderDetailSerializer(order_details, context={"request": request}, many=True).data
        })

    def update(self, request, pk=None):
        """Update order status, including handling order cancellations."""
        order = self.get_object()
        new_status = request.data.get("status")
        previous_status = order.status  # Store previous status before updating

        if not order.is_active:
            return Response({"error": "Cannot update an inactive order"}, status=status.HTTP_400_BAD_REQUEST)

        if new_status == "Cancelled":
            if previous_status in ["Shipped", "Delivered"]:
                return Response({"error": "Order cannot be cancelled at this stage"}, status=status.HTTP_400_BAD_REQUEST)

            order.status = "Cancelled"
            order.is_active = False
            order.save()

            # **Send email only if the previous status was "Processing"**
            if previous_status == "Processing":
                send_mail(
                    subject=f"Refund Request for Order {order.order_id}",
                    message=f"User {order.user.email} has cancelled Order {order.order_id}. Please process the refund manually.",
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[settings.EMAIL_HOST_USER]
                )

            return Response({"message": "Order cancelled successfully."}, status=status.HTTP_200_OK)

        elif new_status == "Shipped":
            self.permission_classes = [IsAdminOrStaff]
            self.check_permissions(request)
            order.status = "Shipped"

            # Reduce stock once order is shipped
            for item in order.order_details.all():
                item.product.stock = F("stock") - item.quantity
                item.product.save()

        elif new_status == "Delivered":
            self.permission_classes = [IsAdminOrStaff]
            self.check_permissions(request)
            order.status = "Delivered"

        else:
            return Response({"error": "Invalid status update"}, status=status.HTTP_400_BAD_REQUEST)

        order.save()
        return Response(OrderSerializer(order, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def payment_webhook(request):
    """Handle Razorpay payment success or failure from GET callback."""
    razorpay_payment_id = request.GET.get("razorpay_payment_id")
    razorpay_payment_link_id = request.GET.get("razorpay_payment_link_id")
    razorpay_payment_link_status = request.GET.get("razorpay_payment_link_status")
    razorpay_payment_link_reference_id = request.GET.get("razorpay_payment_link_reference_id")
    razorpay_signature = request.GET.get("razorpay_signature")

    if not (razorpay_payment_id and razorpay_payment_link_id and razorpay_payment_link_status and razorpay_signature):
        return JsonResponse({"error": "Missing required parameters"}, status=400)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    client.utility.verify_payment_link_signature({
        "payment_link_id": razorpay_payment_link_id,
        "payment_link_reference_id": razorpay_payment_link_reference_id,
        "payment_link_status": razorpay_payment_link_status,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature
    })

    order = Order.objects.filter(razorpay_payment_link_id=razorpay_payment_link_id, is_active=True).first()
    if not order:
        return JsonResponse({"error": "Order not found or inactive"}, status=400)

    if razorpay_payment_link_status == "paid":
        order.status = "Processing"
        order.razorpay_payment_id = razorpay_payment_id
        order.save()

        # Soft delete CartItems after successful payment
        CartItem.objects.filter(cart__user=order.user, is_active=True).update(is_active=False)

        return JsonResponse({"message": "Payment verified, order is now Processing, cart items deactivated"}, status=200)

    elif razorpay_payment_link_status == "failed":
        order.status = "Failed"
        order.save()

    return JsonResponse({"error": "Unknown status received"}, status=400)

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


