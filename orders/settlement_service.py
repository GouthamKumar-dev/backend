"""
Settlement Service
Handles payment settlements to vendors with commission deduction
"""

from django.utils import timezone
from django.db import transaction
from .models import Order, PaymentSettlement
from users.models import VendorAccount
from users.razorpay_service import RazorpayRouteService
from users.utils import create_admin_notification
import logging

logger = logging.getLogger(__name__)


class SettlementService:
    """
    Service for handling payment settlements to vendors
    """
    
    def __init__(self):
        self.razorpay = RazorpayRouteService()
    
    @transaction.atomic
    def process_settlement(self, order: Order):
        """
        Process settlement for an order
        
        Args:
            order: Order instance
            
        Returns:
            PaymentSettlement instance
            
        Raises:
            ValueError: If order doesn't meet settlement requirements
            Exception: If settlement processing fails
        """
        # Validation checks
        if order.status != 'Delivered':
            raise ValueError("Can only settle delivered orders")
        
        if order.settlement_status == 'completed':
            raise ValueError("Order already settled")
        
        if not order.vendor:
            raise ValueError("Order has no associated vendor")
        
        if not order.vendor.kyc_verified:
            raise ValueError("Vendor KYC not verified. Cannot process settlement.")
        
        if not order.vendor.razorpay_account_id:
            raise ValueError("Vendor Razorpay account not linked")
        
        if order.vendor.account_status != 'active':
            raise ValueError(f"Vendor account status is '{order.vendor.account_status}'. Must be 'active'.")
        
        # Calculate commission if not already done
        if order.commission_amount == 0 or order.vendor_settlement_amount == 0:
            order.calculate_commission()
        
        # Check if settlement record already exists
        existing_settlement = PaymentSettlement.objects.filter(order=order).first()
        if existing_settlement and existing_settlement.status in ['processing', 'completed']:
            raise ValueError(f"Settlement already exists with status: {existing_settlement.status}")
        
        # Create or update settlement record
        settlement, created = PaymentSettlement.objects.get_or_create(
            order=order,
            defaults={
                'vendor': order.vendor,
                'order_amount': order.total_price,
                'commission_amount': order.commission_amount,
                'settlement_amount': order.vendor_settlement_amount,
                'status': 'processing'
            }
        )
        
        if not created:
            # Update existing failed settlement
            settlement.vendor = order.vendor
            settlement.order_amount = order.total_price
            settlement.commission_amount = order.commission_amount
            settlement.settlement_amount = order.vendor_settlement_amount
            settlement.status = 'processing'
            settlement.save()
        
        try:
            # Update order settlement status
            order.settlement_status = 'initiated'
            order.save()
            
            # Initiate transfer via Razorpay Route
            transfer = self.razorpay.create_transfer(
                order=order,
                vendor=order.vendor,
                amount=float(order.vendor_settlement_amount)
            )
            
            # Update settlement with transfer details
            settlement.razorpay_transfer_id = transfer['id']
            settlement.razorpay_transfer_response = transfer
            settlement.status = 'completed'
            settlement.completed_at = timezone.now()
            settlement.save()
            
            # Update order with settlement details
            order.settlement_status = 'completed'
            order.razorpay_transfer_id = transfer['id']
            order.settled_at = timezone.now()
            order.save()
            
            # Notify admin about successful settlement
            create_admin_notification(
                user=order.vendor.user,
                title="Settlement Completed",
                message=f"Settlement of ₹{settlement.settlement_amount} completed for order #{order.order_id}",
                event_type="settlement_completed"
            )
            
            logger.info(f"✅ Settlement completed for order {order.order_id}: ₹{settlement.settlement_amount} transferred to vendor {order.vendor.vendor_id}")
            return settlement
            
        except Exception as e:
            # Mark as failed
            settlement.status = 'failed'
            settlement.failure_reason = str(e)
            settlement.save()
            
            order.settlement_status = 'failed'
            order.save()
            
            # Notify admin about failure
            create_admin_notification(
                user=order.vendor.user,
                title="Settlement Failed",
                message=f"Settlement failed for order #{order.order_id}: {str(e)}",
                event_type="settlement_failed"
            )
            
            logger.error(f"❌ Settlement failed for order {order.order_id}: {str(e)}")
            raise
    
    def retry_failed_settlement(self, settlement: PaymentSettlement):
        """
        Retry a failed settlement
        
        Args:
            settlement: PaymentSettlement instance with status='failed'
            
        Returns:
            PaymentSettlement instance
            
        Raises:
            ValueError: If settlement cannot be retried
        """
        if settlement.status != 'failed':
            raise ValueError("Can only retry failed settlements")
        
        if settlement.retry_count >= 3:
            raise ValueError("Maximum retry attempts (3) reached. Manual intervention required.")
        
        # Increment retry count
        settlement.retry_count += 1
        settlement.status = 'processing'
        settlement.failure_reason = None  # Clear previous error
        settlement.save()
        
        logger.info(f"Retrying settlement {settlement.settlement_id} (attempt {settlement.retry_count})")
        
        try:
            return self.process_settlement(settlement.order)
        except Exception as e:
            logger.error(f"Retry {settlement.retry_count} failed for settlement {settlement.settlement_id}: {str(e)}")
            raise
    
    def auto_settle_delivered_orders(self):
        """
        Automatically settle all delivered orders pending settlement
        This can be run as a scheduled task (daily/hourly)
        
        Returns:
            dict: Summary of settlements processed
        """
        # Find all delivered orders that need settlement
        pending_orders = Order.objects.filter(
            status='Delivered',
            settlement_status='pending',
            vendor__isnull=False,
            vendor__kyc_verified=True,
            vendor__account_status='active',
            is_active=True
        ).select_related('vendor')
        
        results = {
            'total': pending_orders.count(),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        logger.info(f"Starting auto-settlement for {results['total']} orders")
        
        for order in pending_orders:
            try:
                # Check if order was delivered at least 24 hours ago (optional safety check)
                # hours_since_delivery = (timezone.now() - order.updated_at).total_seconds() / 3600
                # if hours_since_delivery < 24:
                #     results['skipped'] += 1
                #     continue
                
                self.process_settlement(order)
                results['successful'] += 1
                
            except ValueError as e:
                # Validation errors (expected, not critical)
                results['skipped'] += 1
                logger.warning(f"Skipped order {order.order_id}: {str(e)}")
                
            except Exception as e:
                # Unexpected errors
                results['failed'] += 1
                results['errors'].append({
                    'order_id': order.order_id,
                    'vendor_id': order.vendor.vendor_id if order.vendor else None,
                    'error': str(e)
                })
                logger.error(f"Failed to settle order {order.order_id}: {str(e)}")
        
        # Notify admin with summary
        if results['successful'] > 0 or results['failed'] > 0:
            create_admin_notification(
                user=None,
                title="Auto-Settlement Summary",
                message=f"Processed {results['total']} orders: {results['successful']} successful, {results['failed']} failed, {results['skipped']} skipped",
                event_type="auto_settlement_summary"
            )
        
        logger.info(f"Auto-settlement complete: {results}")
        return results
    
    def reverse_settlement(self, settlement: PaymentSettlement, reason: str = None):
        """
        Reverse a completed settlement (for refunds)
        
        Args:
            settlement: PaymentSettlement instance with status='completed'
            reason: Reason for reversal
            
        Returns:
            dict: Reversal details
        """
        if settlement.status != 'completed':
            raise ValueError("Can only reverse completed settlements")
        
        if not settlement.razorpay_transfer_id:
            raise ValueError("No transfer ID found for this settlement")
        
        try:
            # Reverse the transfer
            reversal = self.razorpay.reverse_transfer(
                settlement.razorpay_transfer_id,
                amount=float(settlement.settlement_amount)
            )
            
            # Update settlement status
            settlement.status = 'reversed'
            settlement.failure_reason = f"Reversed: {reason or 'No reason provided'}"
            settlement.razorpay_transfer_response = {
                **settlement.razorpay_transfer_response,
                'reversal': reversal
            }
            settlement.save()
            
            # Update order
            order = settlement.order
            order.settlement_status = 'pending'  # Reset to pending
            order.razorpay_transfer_id = None
            order.settled_at = None
            order.save()
            
            # Notify admin
            create_admin_notification(
                user=settlement.vendor.user,
                title="Settlement Reversed",
                message=f"Settlement reversed for order #{order.order_id}: {reason or 'Refund processed'}",
                event_type="settlement_reversed"
            )
            
            logger.info(f"Reversed settlement {settlement.settlement_id} for order {order.order_id}")
            return reversal
            
        except Exception as e:
            logger.error(f"Failed to reverse settlement {settlement.settlement_id}: {str(e)}")
            raise
    
    def get_vendor_settlement_summary(self, vendor: VendorAccount, start_date=None, end_date=None):
        """
        Get settlement summary for a vendor
        
        Args:
            vendor: VendorAccount instance
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            dict: Settlement summary with totals
        """
        settlements = PaymentSettlement.objects.filter(vendor=vendor)
        
        if start_date:
            settlements = settlements.filter(initiated_at__gte=start_date)
        if end_date:
            settlements = settlements.filter(initiated_at__lte=end_date)
        
        from django.db.models import Sum, Count
        
        summary = settlements.aggregate(
            total_settlements=Count('settlement_id'),
            total_amount=Sum('settlement_amount'),
            total_commission=Sum('commission_amount'),
            total_order_value=Sum('order_amount')
        )
        
        # Count by status
        status_counts = {}
        for status_choice in PaymentSettlement._meta.get_field('status').choices:
            status = status_choice[0]
            status_counts[status] = settlements.filter(status=status).count()
        
        return {
            **summary,
            'status_breakdown': status_counts,
            'vendor_id': vendor.vendor_id,
            'business_name': vendor.business_name
        }
