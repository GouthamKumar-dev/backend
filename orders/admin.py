from django.contrib import admin
from .models import (
    Cart, CartItem, Order, OrderDetail, 
    PaymentSettlement, DeliveryPartner, OrderLocationHistory
)

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['cart_id', 'user']
    search_fields = ['user__username', 'user__email']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'product', 'quantity', 'is_active']
    list_filter = ['is_active']
    search_fields = ['cart__user__username', 'product__name']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_id', 'user', 'vendor', 'total_price', 'status', 
                   'settlement_status', 'created_at']
    list_filter = ['status', 'settlement_status', 'is_active', 'created_at']
    search_fields = ['order_id', 'user__username', 'user__email', 'tracking_id', 
                    'razorpay_payment_id']
    readonly_fields = ['tracking_id', 'razorpay_payment_link_id', 'razorpay_payment_id',
                      'razorpay_transfer_id', 'created_at', 'updated_at', 'settled_at']
    fieldsets = (
        ('Order Information', {
            'fields': ('user', 'vendor', 'total_price', 'shipping_address', 'status', 'tracking_id')
        }),
        ('Payment Details', {
            'fields': ('razorpay_payment_link_id', 'razorpay_payment_id', 'is_refunded')
        }),
        ('Commission & Settlement', {
            'fields': ('commission_amount', 'vendor_settlement_amount', 'settlement_status',
                      'razorpay_transfer_id', 'settled_at')
        }),
        ('Delivery Tracking', {
            'fields': ('delivery_partner', 'current_location_lat', 'current_location_lng',
                      'estimated_delivery_time')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at')
        }),
    )


@admin.register(OrderDetail)
class OrderDetailAdmin(admin.ModelAdmin):
    list_display = ['order_detail_id', 'order', 'product', 'quantity', 'price_at_purchase', 'is_active']
    list_filter = ['is_active']
    search_fields = ['order__order_id', 'product__name']


@admin.register(PaymentSettlement)
class PaymentSettlementAdmin(admin.ModelAdmin):
    list_display = ['settlement_id', 'order', 'vendor', 'settlement_amount', 
                   'commission_amount', 'status', 'initiated_at']
    list_filter = ['status', 'initiated_at']
    search_fields = ['order__order_id', 'vendor__business_name', 'razorpay_transfer_id']
    readonly_fields = ['razorpay_transfer_id', 'razorpay_transfer_response', 
                      'initiated_at', 'completed_at', 'updated_at']
    fieldsets = (
        ('Order & Vendor', {
            'fields': ('order', 'vendor')
        }),
        ('Amount Details', {
            'fields': ('order_amount', 'commission_amount', 'settlement_amount')
        }),
        ('Razorpay Details', {
            'fields': ('razorpay_transfer_id', 'razorpay_transfer_response')
        }),
        ('Status', {
            'fields': ('status', 'failure_reason', 'retry_count')
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'completed_at', 'updated_at')
        }),
    )


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display = ['partner_id', 'partner_name', 'phone_number', 'status', 
                   'average_rating', 'total_deliveries', 'is_active']
    list_filter = ['status', 'is_active', 'joined_at']
    search_fields = ['partner_name', 'phone_number', 'user__username', 'vehicle_number']
    readonly_fields = ['average_rating', 'total_deliveries', 'joined_at', 'updated_at']
    fieldsets = (
        ('Partner Information', {
            'fields': ('user', 'partner_name', 'phone_number')
        }),
        ('Vehicle Details', {
            'fields': ('vehicle_type', 'vehicle_number')
        }),
        ('Location', {
            'fields': ('current_lat', 'current_lng', 'last_location_update')
        }),
        ('Status & Performance', {
            'fields': ('status', 'is_active', 'average_rating', 'total_deliveries')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at')
        }),
    )


@admin.register(OrderLocationHistory)
class OrderLocationHistoryAdmin(admin.ModelAdmin):
    list_display = ['history_id', 'order', 'delivery_partner', 'latitude', 
                   'longitude', 'status_at_location', 'recorded_at']
    list_filter = ['status_at_location', 'recorded_at']
    search_fields = ['order__order_id', 'delivery_partner__partner_name']
    readonly_fields = ['recorded_at']
