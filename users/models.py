
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
import datetime

class UserRole(models.TextChoices):
    CUSTOMER = 'customer', 'Customer'
    ADMIN = 'admin', 'Admin'
    STAFF = 'staff', 'Staff'

class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, username, email, password=None, role=UserRole.CUSTOMER, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number field must be set')
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(
            phone_number=phone_number, username=username, email=email, role=role, **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, username, email, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self.create_user(phone_number, username, email, password, **extra_fields)

    def get_user(self, user_id):
        """
        Custom method to retrieve user by user_id instead of id.
        """
        print("I am here")
        return self.get(user_id=user_id)


class CustomUser(AbstractBaseUser, PermissionsMixin):

    class Meta:
        db_table = 'users'
        constraints = [
            models.UniqueConstraint(fields=['phone_number', 'email'], name='unique_phone_email_combo')
        ]

    user_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150)  # Not unique
    email = models.EmailField(unique=True)  # Part of unique combo with phone_number
    phone_number = models.CharField(max_length=15, unique=True)  # Must be unique
    default_shipping_address = models.TextField(blank=True, null=True)  # New field
    role = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.CUSTOMER)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    # Use email as the unique identifier
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'phone_number']  # These fields will still be required during user creation

    objects = CustomUserManager()

    def __str__(self):
        return self.username

    @property
    def id(self):
        return self.user_id

    @property
    def is_staff(self):
        return self.role in [UserRole.ADMIN, UserRole.STAFF]

    @property
    def is_superuser(self):
        return self.role == UserRole.ADMIN

class OTP(models.Model):
    identifier = models.CharField(max_length=255, unique=True)  # Phone or email
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    user_data = models.JSONField(null=True, blank=True)

    def is_expired(self):
        """Check if OTP is older than 5 minutes"""
        return timezone.now() > self.created_at + datetime.timedelta(minutes=5)


