from django.contrib import admin
from .models import CustomUser, VendorAccount, KYCVerification, OTP, DeleteAccountOTP, AdminNotification

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'username', 'email', 'phone_number', 'role', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['username', 'email', 'phone_number']
    ordering = ['-created_at']


@admin.register(VendorAccount)
class VendorAccountAdmin(admin.ModelAdmin):
    list_display = ['vendor_id', 'business_name', 'user', 'account_status', 'kyc_verified', 
                   'commission_percentage', 'created_at']
    list_filter = ['account_status', 'kyc_verified', 'is_active', 'created_at']
    search_fields = ['business_name', 'user__username', 'user__email', 'razorpay_account_id']
    readonly_fields = ['razorpay_account_id', 'verified_at', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'business_name', 'business_type')
        }),
        ('Bank Details', {
            'fields': ('bank_account_number', 'bank_ifsc_code', 'bank_account_holder_name', 'bank_name')
        }),
        ('Razorpay Integration', {
            'fields': ('razorpay_account_id', 'razorpay_linked_account_status')
        }),
        ('Status & Verification', {
            'fields': ('account_status', 'kyc_verified', 'is_active', 'verified_at')
        }),
        ('Commission Settings', {
            'fields': ('commission_percentage',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ['kyc_id', 'vendor', 'document_type', 'status', 'submitted_at', 'reviewed_by']
    list_filter = ['status', 'document_type', 'submitted_at']
    search_fields = ['vendor__business_name', 'document_number', 'quickekyc_verification_id']
    readonly_fields = ['quickekyc_verification_id', 'quickekyc_response', 'submitted_at', 'updated_at']
    fieldsets = (
        ('Vendor Information', {
            'fields': ('vendor',)
        }),
        ('Document Details', {
            'fields': ('document_type', 'document_number', 'document_file')
        }),
        ('QuickEKYC Integration', {
            'fields': ('quickekyc_verification_id', 'quickekyc_response')
        }),
        ('Verification Status', {
            'fields': ('status', 'rejection_reason')
        }),
        ('Admin Review', {
            'fields': ('reviewed_by', 'reviewed_at')
        }),
        ('Timestamps', {
            'fields': ('submitted_at', 'updated_at')
        }),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ['identifier', 'otp_code', 'created_at']
    search_fields = ['identifier']
    readonly_fields = ['created_at']


@admin.register(DeleteAccountOTP)
class DeleteAccountOTPAdmin(admin.ModelAdmin):
    list_display = ['email', 'otp_code', 'created_at']
    search_fields = ['email']
    readonly_fields = ['created_at']


@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_type', 'user', 'is_read', 'created_at']
    list_filter = ['is_read', 'event_type', 'created_at']
    search_fields = ['title', 'message']
    readonly_fields = ['created_at']
