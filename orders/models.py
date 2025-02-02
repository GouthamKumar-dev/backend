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
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)  # Soft delete flag for orders

    def __str__(self):
        return f"Order #{self.order_id} by {self.user.username}"

# OrderDetail Model
class OrderDetail(models.Model):
    class Meta:
        db_table = 'order_details'

    order_detail_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_details")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)  # Soft delete flag for order details

    def __str__(self):
        return f"{self.quantity} x {self.product.name} for Order #{self.order.order_id}"
