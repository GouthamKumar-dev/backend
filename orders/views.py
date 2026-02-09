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
from users.models import CustomUser, UserRole
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import hmac
import hashlib
import json
from ecommerce.logger import logger
from django.db.models import F
from django.core.mail import send_mail
import time
from users.utils import create_admin_notification
from rest_framework.pagination import PageNumberPagination
from .tracking_service import DeliveryTrackingService
from .models import DeliveryPartner, OrderLocationHistory

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
        #  Notify Admin on manual delete
       


        # Return success response
        return Response({"message": "Cart item marked as inactive"}, status=status.HTTP_204_NO_CONTENT)

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ["get", "post", "put"]

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.ADMIN:
            # Admins only see orders for their products
            return Order.objects.filter(admin=user).order_by("-created_at")
        elif user.role == UserRole.STAFF or user.role == 'owner':
            # Staff and owner see all orders
            return Order.objects.all().order_by("-created_at")
        # Customers see only their own orders
        return Order.objects.filter(user=user).order_by("-created_at")

    @transaction.atomic
    def create(self, request):
        """
        Create orders and generate Razorpay Payment Links.
        NOW SUPPORTS MULTI-ADMIN CART:
        - Groups cart items by admin
        - Creates separate order for each admin
        - Generates individual payment links for each order
        - Returns list of orders with their payment links
        """
        user = request.user
        cart = Cart.objects.filter(user=user).first()
        cart_items = CartItem.objects.filter(cart=cart, is_active=True)

        if not cart or not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        shipping_address = request.data.get("shipping_address")
        if not shipping_address:
            return Response({"error": "Shipping address is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ========== NEW: GROUP CART ITEMS BY ADMIN ==========
        admin_groups = {}
        for item in cart_items:
            admin = item.product.admin
            
            if not admin:
                return Response(
                    {"error": f"Product '{item.product.name}' is not associated with any admin"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            admin_id = admin.id
            if admin_id not in admin_groups:
                admin_groups[admin_id] = {
                    'admin': admin,
                    'items': [],
                    'total_price': 0
                }
            
            admin_groups[admin_id]['items'].append(item)
            admin_groups[admin_id]['total_price'] += item.product.offer_price * item.quantity

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        created_orders = []

        try:
            # ========== CREATE SEPARATE ORDER FOR EACH ADMIN ==========
            for admin_id, group_data in admin_groups.items():
                admin = group_data['admin']
                items = group_data['items']
                total_price = group_data['total_price']

                # Create order for this admin
                order = Order.objects.create(
                    user=user,
                    admin=admin,
                    total_price=total_price,
                    shipping_address=shipping_address,
                    status="Pending"
                )
                
                # Calculate commission automatically (2% platform, 98% admin)
                order.calculate_commission()

                # Add order items
                for item in items:
                    OrderDetail.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        price_at_purchase=item.product.offer_price
                    )

                # Create Razorpay Payment Link for this order
                payment_link = client.payment_link.create({
                    "amount": int(total_price * 100),  # Convert to paise
                    "currency": "INR",
                    "description": f"Order #{order.order_id} from {admin.username}",
                    "customer": {
                        "name": user.username,
                        "email": user.email,
                        "contact": user.phone_number,
                    }
                })

                # Save payment link ID
                order.razorpay_payment_link_id = payment_link["id"]
                order.save()
                
                # Notify admin about new order
                create_admin_notification(
                    title="order_creation",
                    user=request.user,
                    message=f"New order placed: #{order.order_id} (Total: ₹{total_price})",
                    event_type="order_created"
                )

                # Add to response list
                created_orders.append({
                    "order_id": order.order_id,
                    "payment_link_id": payment_link["id"],
                    "payment_link": payment_link["short_url"],
                    "total_price": str(total_price),
                    "admin_id": admin.id,
                    "admin_name": admin.username,
                    "item_count": len(items),
                    "commission_amount": str(order.commission_amount),
                    "admin_settlement_amount": str(order.admin_settlement_amount),
                    "settlement_status": order.settlement_status,
                    "products": [
                        {
                            "product_id": item.product.product_id,
                            "name": item.product.name,
                            "quantity": item.quantity,
                            "price": str(item.product.offer_price)
                        }
                        for item in items
                    ]
                })

            # Prepare response
            response_data = {
                "success": True,
                "message": f"Successfully created {len(created_orders)} order(s)",
                "order_count": len(created_orders),
                "orders": created_orders,
                "grouped_by_admins": True
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating orders: {str(e)}")
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
            # If payment ID is not provided, fetch the latest one using payment link
            if not razorpay_payment_id:
                payments_response = client.payment_link.fetch(razorpay_payment_link_id)
                payments = payments_response.get("payments", [])

                if not payments:
                    return Response({"error": "No payments found for this link"}, status=status.HTTP_400_BAD_REQUEST)

                logger.info(f"payments:{payments[0]}")
                razorpay_payment_id = payments[0]["payment_id"]  # Get the latest payment ID

            # Poll Razorpay API up to 5 times to check payment status
            for _ in range(5):
                payment = client.payment.fetch(razorpay_payment_id)
                logger.info(f"Payment status at the moment is {payment['status']} for payment id : {razorpay_payment_id}")

                if payment["status"] == "captured":
                    order.status = "Processing"
                    order.razorpay_payment_id = razorpay_payment_id
                    order.save()

                    # Mark cart items as inactive
                    CartItem.objects.filter(cart__user=order.user, is_active=True).update(is_active=False)

                    return Response({"message": "Payment verified successfully"}, status=status.HTTP_200_OK)

                elif payment["status"] in ["failed", "refunded"]:
                    order.status = "Failed"
                    order.razorpay_payment_id = razorpay_payment_id
                    order.save()
                    return Response({"error": f"Payment {payment['status']}"}, status=status.HTTP_400_BAD_REQUEST)

                time.sleep(3)  # Wait 3 seconds before retrying

            return Response({"error": "Payment still pending"}, status=status.HTTP_400_BAD_REQUEST)

        except razorpay.errors.BadRequestError:
            return Response({"error": "Invalid payment details"}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        order_details = order.order_details.filter(is_active=True)

        return Response({
            "order_id": order.order_id,
            "total_price":  sum(detail.product.offer_price * detail.quantity for detail in  order_details),
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
            # ✅ Notify admin about cancellation
            create_admin_notification(
                title="order_cancelation",
                user=order.user,
                message=f"Order {order.order_id} was cancelled.",
                event_type="order_cancelled"
                
            )

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
        # ✅ Notify admin about status update
        create_admin_notification(
            title="order_status",
            user=order.user,
            message=f"Order {order.order_id} status updated to '{new_status}'.",
            event_type="order_status_update"
        )
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


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def razorpay_webhook(request):
    """
    Handle Razorpay webhook events (POST requests)
    This endpoint receives events like payment.authorized, payment.captured, payment.failed, etc.
    """
    try:
        # Get the webhook signature from headers
        webhook_signature = request.headers.get('X-Razorpay-Signature')
        webhook_secret = settings.WEBHOOK_SECRET
        
        # Get the raw body
        webhook_body = request.body
        
        # Verify webhook signature for security
        if webhook_secret:
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                webhook_body,
                hashlib.sha256
            ).hexdigest()
            
            if webhook_signature != expected_signature:
                logger.warning("Invalid webhook signature received")
                return JsonResponse({"error": "Invalid signature"}, status=400)
        
        # Parse the webhook payload
        payload = json.loads(webhook_body.decode('utf-8'))
        event = payload.get('event')
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        
        logger.info(f"Webhook event received: {event}")
        logger.info(f"Payment entity: {payment_entity}")
        
        # Extract payment details
        payment_id = payment_entity.get('id')
        order_id = payment_entity.get('order_id')  # Razorpay order_id
        payment_status = payment_entity.get('status')
        amount = payment_entity.get('amount', 0) / 100  # Convert paise to rupees
        
        # Handle different webhook events
        if event == 'payment.authorized':
            # Payment has been authorized (but not captured yet)
            logger.info(f"Payment authorized: {payment_id}")
            # You can update order status here if needed
            
        elif event == 'payment.captured':
            # Payment has been successfully captured
            logger.info(f"Payment captured: {payment_id} for amount: {amount}")
            
            # Find the order by razorpay_order_id or payment_link_id
            order = Order.objects.filter(
                razorpay_order_id=order_id, 
                is_active=True
            ).first()
            
            if not order:
                # Try finding by payment_id
                order = Order.objects.filter(
                    razorpay_payment_id=payment_id,
                    is_active=True
                ).first()
            
            if order:
                order.status = "Processing"
                order.razorpay_payment_id = payment_id
                order.save()
                
                # Soft delete cart items
                CartItem.objects.filter(
                    cart__user=order.user, 
                    is_active=True
                ).update(is_active=False)
                
                logger.info(f"Order {order.order_id} marked as Processing")
            else:
                logger.warning(f"Order not found for payment_id: {payment_id}")
        
        elif event == 'payment.failed':
            # Payment has failed
            logger.warning(f"Payment failed: {payment_id}")
            
            order = Order.objects.filter(
                razorpay_order_id=order_id,
                is_active=True
            ).first()
            
            if order:
                order.status = "Failed"
                order.save()
                logger.info(f"Order {order.order_id} marked as Failed")
        
        elif event == 'order.paid':
            # Order has been paid
            logger.info(f"Order paid event: {order_id}")
            
        elif event == 'payment.dispute.created':
            # A dispute has been created for a payment
            logger.warning(f"Dispute created for payment: {payment_id}")
            # You can add logic to notify admin
            
        elif event == 'refund.created':
            # A refund has been created
            logger.info(f"Refund created for payment: {payment_id}")
            
        # Return success response
        return JsonResponse({"status": "success", "event": event}, status=200)
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


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


# ========== SETTLEMENT MANAGEMENT APIs ==========
from .settlement_service import SettlementService
from .models import PaymentSettlement
from .serializers import PaymentSettlementSerializer
from users.models import VendorAccount


@api_view(['POST'])
@permission_classes([IsAdminOrStaff])
def initiate_settlement(request, order_id):
    """
    Manually initiate settlement for an order (Admin/Staff only)
    POST /api/settlements/initiate/{order_id}/
    """
    try:
        order = Order.objects.select_related('vendor', 'user').get(order_id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    settlement_service = SettlementService()
    
    try:
        settlement = settlement_service.process_settlement(order)
        return Response(
            {
                "success": True,
                "message": f"Settlement completed successfully. ₹{settlement.settlement_amount} transferred to vendor.",
                "settlement": PaymentSettlementSerializer(settlement).data
            },
            status=status.HTTP_200_OK
        )
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Settlement error for order {order_id}: {str(e)}")
        return Response(
            {"error": f"Settlement failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_settlement_history(request):
    """
    Get settlement history
    GET /api/settlements/
    
    Owner/Staff: See all settlements
    Admin: See their own settlements
    Query params: ?status=completed&admin_id=5
    """
    user_role = request.user.role
    
    if user_role in ['owner', UserRole.STAFF]:
        # Owner and staff can see all settlements
        settlements = PaymentSettlement.objects.all().select_related(
            'order', 'admin', 'order__user'
        )
        
        # Filters
        status_filter = request.GET.get('status')
        if status_filter:
            settlements = settlements.filter(status=status_filter)
        
        admin_id = request.GET.get('admin_id')
        if admin_id:
            settlements = settlements.filter(admin_id=admin_id)
            
    elif user_role == UserRole.ADMIN:
        # Admins can only see their own settlements
        settlements = PaymentSettlement.objects.filter(
            admin=request.user
        ).select_related('order', 'order__user')
        
        # Optional status filter
        status_filter = request.GET.get('status')
        if status_filter:
            settlements = settlements.filter(status=status_filter)
    else:
        return Response(
            {"error": "Not authorized. Only admins, staff, and owner can view settlements."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Pagination
    paginator = CartItemPagination()
    paginated_settlements = paginator.paginate_queryset(settlements.order_by('-initiated_at'), request)
    
    serializer = PaymentSettlementSerializer(paginated_settlements, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminOrStaff])
def retry_settlement(request, settlement_id):
    """
    Retry a failed settlement (Admin/Staff only)
    POST /api/settlements/{settlement_id}/retry/
    """
    try:
        settlement = PaymentSettlement.objects.select_related('order', 'vendor').get(
            settlement_id=settlement_id
        )
    except PaymentSettlement.DoesNotExist:
        return Response(
            {"error": "Settlement not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    settlement_service = SettlementService()
    
    try:
        updated_settlement = settlement_service.retry_failed_settlement(settlement)
        return Response(
            {
                "success": True,
                "message": "Settlement retry completed successfully",
                "settlement": PaymentSettlementSerializer(updated_settlement).data
            },
            status=status.HTTP_200_OK
        )
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Retry settlement error: {str(e)}")
        return Response(
            {"error": f"Retry failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminOrStaff])
def auto_settle_all(request):
    """
    Trigger automatic settlement for all eligible orders (Admin only)
    POST /api/settlements/auto-settle/
    """
    settlement_service = SettlementService()
    
    try:
        results = settlement_service.auto_settle_delivered_orders()
        return Response({
            "success": True,
            "message": "Auto-settlement completed",
            "results": results
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Auto-settlement error: {str(e)}")
        return Response(
            {"error": f"Auto-settlement failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_vendor_settlement_summary(request, vendor_id=None):
    """
    Get settlement summary for a vendor
    GET /api/settlements/summary/{vendor_id}/ - Admin/Staff for any vendor
    GET /api/settlements/summary/ - Vendor for their own summary
    Query params: ?start_date=2026-01-01&end_date=2026-01-31
    """
    if vendor_id:
        # Admin/Staff accessing specific vendor
        if request.user.role not in [UserRole.ADMIN, UserRole.STAFF]:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            vendor = VendorAccount.objects.get(vendor_id=vendor_id)
        except VendorAccount.DoesNotExist:
            return Response(
                {"error": "Vendor not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Vendor accessing their own summary
        try:
            vendor = VendorAccount.objects.get(user=request.user)
        except VendorAccount.DoesNotExist:
            return Response(
                {"error": "Not a vendor"},
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Date filters
    from datetime import datetime
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        start_date = datetime.fromisoformat(start_date)
    if end_date:
        end_date = datetime.fromisoformat(end_date)
    
    settlement_service = SettlementService()
    summary = settlement_service.get_vendor_settlement_summary(
        vendor, start_date, end_date
    )
    
    return Response(summary, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def reverse_settlement(request, settlement_id):
    """
    Reverse a completed settlement (Admin only, for refunds)
    POST /api/settlements/{settlement_id}/reverse/
    
    Request Body:
    {
        "reason": "Customer refund - product damaged"
    }
    """
    try:
        settlement = PaymentSettlement.objects.select_related('order', 'vendor').get(
            settlement_id=settlement_id
        )
    except PaymentSettlement.DoesNotExist:
        return Response(
            {"error": "Settlement not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    reason = request.data.get('reason', 'No reason provided')
    
    settlement_service = SettlementService()
    
    try:
        reversal = settlement_service.reverse_settlement(settlement, reason)
        return Response({
            "success": True,
            "message": "Settlement reversed successfully",
            "reversal": reversal
        }, status=status.HTTP_200_OK)
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Reverse settlement error: {str(e)}")
        return Response(
            {"error": f"Reversal failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# PHASE 4: Real-Time Order Tracking APIs
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_delivery_location(request, order_id):
    """
    Update delivery partner's current location for an order.
    POST /api/orders/{order_id}/location/update/
    
    Body:
    {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy": 10.5,
        "speed": 25.0,  // km/h (optional)
        "heading": 90.0  // degrees (optional)
    }
    """
    try:
        order = Order.objects.select_related('delivery_partner').get(order_id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify user is delivery partner for this order
    if not order.delivery_partner or order.delivery_partner.user != request.user:
        return Response(
            {"error": "Only assigned delivery partner can update location"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    accuracy = request.data.get('accuracy', 0)
    speed = request.data.get('speed')
    heading = request.data.get('heading')
    
    if not latitude or not longitude:
        return Response(
            {"error": "Latitude and longitude are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    tracking_service = DeliveryTrackingService()
    location = tracking_service.record_location_update(
        order_id, latitude, longitude, accuracy, speed, heading
    )
    
    if location:
        return Response({
            "success": True,
            "message": "Location updated successfully",
            "location_id": location.location_id,
            "timestamp": location.timestamp.isoformat()
        }, status=status.HTTP_200_OK)
    else:
        return Response(
            {"error": "Failed to update location"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_tracking(request, order_id):
    """
    Get real-time tracking information for an order.
    GET /api/orders/{order_id}/tracking/
    
    Response:
    {
        "order_id": 123,
        "status": "Out for Delivery",
        "current_location": {...},
        "location_history": [...],
        "eta": {...},
        "delivery_partner": {...}
    }
    """
    try:
        order = Order.objects.select_related('delivery_partner', 'user').get(order_id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permission: order owner, delivery partner, or admin
    if order.user != request.user and \
       (not order.delivery_partner or order.delivery_partner.user != request.user) and \
       not (request.user.is_staff or request.user.is_superuser):
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    tracking_service = DeliveryTrackingService()
    
    # Get current location
    current_location = tracking_service.get_current_location(order_id)
    
    # Get location history (last 50 points)
    location_history = tracking_service.get_location_history(order_id, limit=50)
    
    # Calculate ETA (assuming destination from shipping address)
    # Note: In production, you'd parse shipping address to get GPS coordinates
    eta_data = None
    if current_location:
        # Placeholder destination coordinates (replace with actual address geocoding)
        dest_lat = 12.9716  # Example: Bangalore coordinates
        dest_lon = 77.5946
        eta_data = tracking_service.calculate_order_eta(order_id, dest_lat, dest_lon)
    
    response_data = {
        "order_id": order.order_id,
        "status": order.status,
        "shipping_address": order.shipping_address,
        "total_price": str(order.total_price),
        "created_at": order.created_at.isoformat(),
        "current_location": current_location,
        "location_history": location_history,
        "eta": eta_data
    }
    
    # Add delivery partner info
    if order.delivery_partner:
        response_data["delivery_partner"] = {
            "name": order.delivery_partner.name,
            "phone_number": order.delivery_partner.phone_number,
            "vehicle_type": order.delivery_partner.vehicle_type,
            "vehicle_number": order.delivery_partner.vehicle_number
        }
    
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_delivery_route(request, order_id):
    """
    Get complete delivery route with statistics.
    GET /api/orders/{order_id}/route/
    
    Response:
    {
        "route": [[lat1, lon1], [lat2, lon2], ...],
        "statistics": {
            "total_distance_km": 15.5,
            "duration_minutes": 45,
            "average_speed_kmh": 20.6
        }
    }
    """
    try:
        order = Order.objects.get(order_id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permission
    if order.user != request.user and not (request.user.is_staff or request.user.is_superuser):
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    tracking_service = DeliveryTrackingService()
    
    route = tracking_service.get_delivery_route(order_id, max_points=200)
    statistics = tracking_service.calculate_route_statistics(order_id)
    
    return Response({
        "order_id": order_id,
        "route": route,
        "statistics": statistics
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def assign_delivery_partner(request, order_id):
    """
    Manually assign delivery partner to an order (Admin only).
    POST /api/orders/{order_id}/assign-partner/
    
    Body:
    {
        "partner_id": 5
    }
    
    OR auto-assign nearest:
    {
        "auto_assign": true,
        "pickup_latitude": 12.9716,
        "pickup_longitude": 77.5946
    }
    """
    try:
        order = Order.objects.get(order_id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.data.get('auto_assign'):
        # Auto-assign nearest partner
        pickup_lat = request.data.get('pickup_latitude')
        pickup_lon = request.data.get('pickup_longitude')
        
        if not pickup_lat or not pickup_lon:
            return Response(
                {"error": "Pickup coordinates required for auto-assignment"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tracking_service = DeliveryTrackingService()
        partner = tracking_service.auto_assign_delivery_partner(
            order_id, pickup_lat, pickup_lon
        )
        
        if partner:
            return Response({
                "success": True,
                "message": f"Delivery partner '{partner.name}' assigned automatically",
                "partner": {
                    "partner_id": partner.partner_id,
                    "name": partner.name,
                    "phone_number": partner.phone_number,
                    "vehicle_type": partner.vehicle_type
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "No available delivery partners found nearby"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    else:
        # Manual assignment
        partner_id = request.data.get('partner_id')
        
        if not partner_id:
            return Response(
                {"error": "partner_id required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            partner = DeliveryPartner.objects.get(partner_id=partner_id)
        except DeliveryPartner.DoesNotExist:
            return Response(
                {"error": "Delivery partner not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        order.delivery_partner = partner
        order.status = 'Shipped'
        order.save()
        
        return Response({
            "success": True,
            "message": f"Delivery partner '{partner.name}' assigned to order",
            "partner": {
                "partner_id": partner.partner_id,
                "name": partner.name,
                "phone_number": partner.phone_number
            }
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_nearby_partners(request):
    """
    Find delivery partners near a location (Admin only).
    GET /api/delivery-partners/nearby/?latitude=12.9716&longitude=77.5946&radius=5
    
    Query Params:
    - latitude: Search center latitude
    - longitude: Search center longitude
    - radius: Search radius in km (default 5)
    - available_only: true/false (default true)
    """
    latitude = request.GET.get('latitude')
    longitude = request.GET.get('longitude')
    radius = float(request.GET.get('radius', 5.0))
    available_only = request.GET.get('available_only', 'true').lower() == 'true'
    
    if not latitude or not longitude:
        return Response(
            {"error": "Latitude and longitude required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    tracking_service = DeliveryTrackingService()
    nearby_partners = tracking_service.get_nearby_delivery_partners(
        float(latitude), float(longitude), radius, available_only
    )
    
    return Response({
        "search_location": {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "radius_km": radius
        },
        "partners_found": len(nearby_partners),
        "partners": nearby_partners
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_delivery_partner_orders(request):
    """
    Get all orders assigned to logged-in delivery partner.
    GET /api/delivery-partner/orders/
    
    Query Params:
    - status: Filter by status (Shipped, Out for Delivery, etc.)
    """
    try:
        partner = DeliveryPartner.objects.get(user=request.user)
    except DeliveryPartner.DoesNotExist:
        return Response(
            {"error": "User is not a delivery partner"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    orders = Order.objects.filter(delivery_partner=partner)
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    orders = orders.order_by('-created_at')
    
    order_data = []
    for order in orders:
        tracking_service = DeliveryTrackingService()
        current_location = tracking_service.get_current_location(order.order_id)
        
        order_data.append({
            "order_id": order.order_id,
            "status": order.status,
            "shipping_address": order.shipping_address,
            "total_price": str(order.total_price),
            "created_at": order.created_at.isoformat(),
            "current_location": current_location
        })
    
    return Response({
        "partner_name": partner.name,
        "total_orders": len(order_data),
        "orders": order_data
    }, status=status.HTTP_200_OK)




