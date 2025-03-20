from django.db import models
from django.db.models import Q, UniqueConstraint
from users.models import CustomUser
import os
import uuid

class Category(models.Model):
    class Meta:
        db_table = 'category'
        constraints = [
            UniqueConstraint(
                fields=["category_code"],
                condition=Q(is_active=True),
                name="unique_active_category_code"
            )
        ]

    category_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    category_code = models.CharField(max_length=100, default=None, blank=True, null=True)  # No unique=True here
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.category_code:
            self.category_code = f"CAT-{uuid.uuid4().hex[:8]}"  # Generate default category_code
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    class Meta:
        db_table = 'products'
        constraints = [
            UniqueConstraint(
                fields=["product_code"],
                condition=Q(is_active=True),
                name="unique_active_product_code"
            )
        ]

    product_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    stock = models.PositiveIntegerField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    product_code = models.CharField(max_length=100, default=None, blank=True, null=True)  # No unique=True here
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def get_offer_price(self):
        """Calculate offer price based on discount percentage."""
        if not self.discount_percentage:  # Handles None or 0 cases
            return int(self.price)  # Return original price if no discount
        return int(self.price - (self.price * self.discount_percentage / 100)) 

    def save(self, *args, **kwargs):
        if not self.product_code:
            self.product_code = f"PROD-{uuid.uuid4().hex[:8]}"  # Generate default product_code
            
        self.offer_price = round(self.price - (self.price * self.discount_percentage / 100), 2)
    
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def favorite_count(self):
        return self.favorites.filter(is_active=True).count()  # Count how many users have favorited this product


class Favorite(models.Model):
    class Meta:
        db_table = 'favorites'
        unique_together = ('user', 'product')  # Prevent duplicate favorites

    favorite_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} -> {self.product.name}"

def upload_to(instance, filename):
    """
    Function to upload only PNG files to the media/uploads/ folder.
    """
    base, extension = os.path.splitext(filename)
    if extension.lower() != ".png":
        raise ValueError("Only PNG images are allowed.")  # Restrict uploads to PNG only

    return f'uploads/{filename}'  # Store images in the 'media/uploads/' folder

class UploadedImage(models.Model):

    class Meta:
        db_table = 'images'

    image = models.ImageField(upload_to=upload_to)  # Store images only in PNG format
    product = models.ForeignKey('Product', null=True, blank=True, on_delete=models.CASCADE)
    category = models.ForeignKey('Category', null=True, blank=True, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product or self.category}"

    def get_image_url(self):
        """ Return the full URL for the stored image """
        if self.image:
            return self.image.url
        return None
