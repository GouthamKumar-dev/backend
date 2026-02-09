from django.db import models
from users.models import CustomUser
from products.models import Product
import uuid

# Cart Model
class Cart(models.Model):
    class Meta:
        db_table = 'cart'

    cart_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='cart')  # One cart per user
    # No ManyToManyField, as only one cart per user

    def __str__(self):
        return f"Cart of {self.user.username}"

# CartItem Model (for handling quantity and is_active flag)
class CartItem(models.Model):
    class Meta:
        db_table = 'cart_items'

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.quantity} of {self.product.name} in cart {self.cart.cart_id}"

# Order Model
class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Failed', 'Failed'),
        ('Cancelled', 'Cancelled'),
    ]

    class Meta:
        db_table = 'orders'

    order_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.TextField(max_length=250)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    tracking_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    razorpay_payment_link_id = models.CharField(max_length=255, blank=True, null=True)  # Payment Link ID
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)  # Set after payment
    is_refunded = models.BooleanField(default=False)  # Track refunds
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)  # Soft delete flag for orders
    
    # ========== ADMIN & COMMISSION TRACKING (renamed from vendor) ==========
    admin = models.ForeignKey(
        'users.CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='admin_orders',
        limit_choices_to={'role': 'admin'}
    )
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)  # Platform commission (2%)
    admin_settlement_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)  # Amount to transfer to admin (98%)
    settlement_status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Pending Settlement'),
            ('initiated', 'Settlement Initiated'),
            ('completed', 'Settlement Completed'),
            ('failed', 'Settlement Failed'),
        ],
        default='pending'
    )
    razorpay_transfer_id = models.CharField(max_length=255, blank=True, null=True)  # Razorpay Route Transfer ID
    settled_at = models.DateTimeField(blank=True, null=True)
    
    # ========== NEW: DELIVERY TRACKING ==========
    delivery_partner = models.ForeignKey('DeliveryPartner', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    current_location_lat = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    current_location_lng = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    estimated_delivery_time = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Order #{self.order_id} by {self.user.username}"
    
    def calculate_commission(self):
        """Calculate commission - 2% to platform owner, 98% to admin"""
        commission_percentage = 2.0  # Fixed 2% platform commission
        
        self.commission_amount = (self.total_price * commission_percentage) / 100
        self.admin_settlement_amount = self.total_price - self.commission_amount
        self.save()

# OrderDetail Model
class OrderDetail(models.Model):
    class Meta:
        db_table = 'order_details'

    order_detail_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_details")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, help_text="Stores the offer price at purchase")
    is_active = models.BooleanField(default=True)  # Soft delete flag for order details

    def save(self, *args, **kwargs):
        """Ensure price_at_purchase is the offer price at the time of purchase"""
        if not self.price_at_purchase:  # Only set if not already provided
            self.price_at_purchase = self.product.offer_price  # Store the offer price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product.name} for Order #{self.order.order_id}"


# ========== PAYMENT SETTLEMENT TRACKING ==========
class PaymentSettlement(models.Model):
    """
    Tracks all payment settlements/transfers from master account to admin accounts.
    Platform collects 2% commission, admin receives 98%.
    """
    SETTLEMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    
    settlement_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='settlements')
    admin = models.ForeignKey(
        'users.CustomUser', 
        on_delete=models.CASCADE, 
        related_name='admin_settlements',
        limit_choices_to={'role': 'admin'},
        null=True,  # Temporary for migration
        blank=True
    )
    
    # Amount Details
    order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)  # 2% to platform
    settlement_amount = models.DecimalField(max_digits=10, decimal_places=2)  # 98% to admin
    
    # Razorpay Route Details
    razorpay_transfer_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    razorpay_transfer_response = models.JSONField(blank=True, null=True)  # Store full API response
    
    # Status & Tracking
    status = models.CharField(max_length=20, choices=SETTLEMENT_STATUS_CHOICES, default='pending')
    failure_reason = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_settlements'
        ordering = ['-initiated_at']
    
    def __str__(self):
        return f"Settlement #{self.settlement_id} - Order #{self.order.order_id} (₹{self.settlement_amount})"


# ========== DELIVERY PARTNER MANAGEMENT ==========
class DeliveryPartner(models.Model):
    """
    Delivery partners who handle order deliveries with real-time tracking.
    """
    PARTNER_STATUS_CHOICES = [
        ('available', 'Available'),
        ('on_delivery', 'On Delivery'),
        ('offline', 'Offline'),
        ('suspended', 'Suspended'),
    ]
    
    partner_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='delivery_partner')
    
    # Partner Details
    partner_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)
    vehicle_type = models.CharField(max_length=50, blank=True, null=True)  # Bike, Car, etc.
    vehicle_number = models.CharField(max_length=20, blank=True, null=True)
    
    # Current Location
    current_lat = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    current_lng = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    last_location_update = models.DateTimeField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=PARTNER_STATUS_CHOICES, default='available')
    is_active = models.BooleanField(default=True)
    
    # Ratings & Performance
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    total_deliveries = models.IntegerField(default=0)
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'delivery_partners'
    
    def __str__(self):
        return f"{self.partner_name} - {self.status}"


# ========== ORDER LOCATION HISTORY ==========
class OrderLocationHistory(models.Model):
    """
    Tracks the real-time location history of an order for map visualization.
    """
    history_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='location_history')
    delivery_partner = models.ForeignKey(DeliveryPartner, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Location Data
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    
    # Additional Info
    status_at_location = models.CharField(max_length=50, blank=True, null=True)  # "Picked up", "In transit", etc.
    notes = models.TextField(blank=True, null=True)
    
    # Timestamp
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_location_history'
        ordering = ['-recorded_at']
    
    def __str__(self):
        return f"Order #{self.order.order_id} at ({self.latitude}, {self.longitude})"
