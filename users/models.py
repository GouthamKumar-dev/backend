
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
import datetime
from django.conf import settings

class UserRole(models.TextChoices):
    CUSTOMER = 'customer', 'Customer'
    ADMIN = 'admin', 'Admin'
    STAFF = 'staff', 'Staff'
    OWNER = 'owner', 'Owner'  # Platform owner who collects 2% commission

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
    
    # Bank Details (For Admin settlements)
    bank_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_ifsc_code = models.CharField(max_length=11, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_branch = models.CharField(max_length=255, blank=True, null=True)
    
    # Alternative payment methods
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    
    # KYC/Verification details
    pan_number = models.CharField(max_length=10, blank=True, null=True)
    gstin = models.CharField(max_length=15, blank=True, null=True)
    
    # Verification status
    bank_details_verified = models.BooleanField(default=False)
    bank_verified_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_banks')
    bank_verified_at = models.DateTimeField(null=True, blank=True)

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

class DeleteAccountOTP(models.Model):
    """Separate OTP model for account deletion to keep it independent from login OTP"""
    email = models.CharField(max_length=255, unique=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        """Check if OTP is older than 5 minutes"""
        return timezone.now() > self.created_at + datetime.timedelta(minutes=5)
    
    class Meta:
        db_table = 'users_delete_account_otp'
    
    #notification for admin
class AdminNotification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,  # Optional: allow null if not always set
        blank=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    event_type = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'users_adminnotification' 

    def __str__(self):
        return f"{self.title} - {self.created_at}"


# ========== VENDOR/BENEFICIARY MANAGEMENT ==========
class VendorAccount(models.Model):
    """
    Represents a vendor/store owner who will receive settlements after commission deduction.
    Each vendor needs KYC verification before receiving payments.
    """
    ACCOUNT_STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
    ]
    
    vendor_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='vendor_account')
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=100, blank=True, null=True)  # Retailer, Wholesaler, etc.
    
    # Razorpay Linked Account Details
    razorpay_account_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    razorpay_linked_account_status = models.CharField(max_length=50, blank=True, null=True)
    
    # Bank Account Details
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    bank_account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Status & Verification
    account_status = models.CharField(max_length=20, choices=ACCOUNT_STATUS_CHOICES, default='pending')
    kyc_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Commission Settings (can be customized per vendor)
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)  # Default 2%
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'vendor_accounts'
    
    def __str__(self):
        return f"{self.business_name} ({self.user.username})"


# ========== KYC VERIFICATION ==========
class KYCVerification(models.Model):
    """
    Stores KYC verification details for vendors using QuickEKYC API.
    """
    KYC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_review', 'In Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('resubmit', 'Resubmit Required'),
    ]
    
    DOCUMENT_TYPE_CHOICES = [
        ('aadhaar', 'Aadhaar Card'),
        ('pan', 'PAN Card'),
        ('bank_statement', 'Bank Statement'),
        ('business_proof', 'Business Proof'),
        ('gst_certificate', 'GST Certificate'),
    ]
    
    kyc_id = models.AutoField(primary_key=True)
    vendor = models.ForeignKey(VendorAccount, on_delete=models.CASCADE, related_name='kyc_documents')
    
    # Document Details
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    document_number = models.CharField(max_length=100, blank=True, null=True)
    document_file = models.FileField(upload_to='kyc_documents/', blank=True, null=True)
    
    # QuickEKYC Integration
    quickekyc_verification_id = models.CharField(max_length=255, blank=True, null=True)
    quickekyc_response = models.JSONField(blank=True, null=True)  # Store API response
    
    # Verification Status
    status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Admin Review
    reviewed_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_kyc_documents'
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kyc_verifications'
        unique_together = ('vendor', 'document_type')
    
    def __str__(self):
        return f"{self.vendor.business_name} - {self.document_type} ({self.status})"


