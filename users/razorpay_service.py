"""
Razorpay Route Service
Handles linked account creation and fund transfers for vendor settlements
"""

import razorpay
from django.conf import settings
from .models import VendorAccount
import logging

logger = logging.getLogger(__name__)


class RazorpayRouteService:
    """
    Service class for handling Razorpay Route operations
    """
    
    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    
    def create_linked_account(self, vendor: VendorAccount):
        """
        Create a Razorpay linked account for a vendor
        
        Args:
            vendor: VendorAccount instance
            
        Returns:
            dict: Razorpay account details
            
        Raises:
            razorpay.errors.BadRequestError: If account creation fails
        """
        try:
            # Prepare account data
            account_data = {
                "email": vendor.user.email,
                "phone": vendor.user.phone_number,
                "type": "route",
                "reference_id": f"vendor_{vendor.vendor_id}",
                "legal_business_name": vendor.business_name,
                "business_type": vendor.business_type or "individual",
                "contact_name": vendor.user.username,
                "profile": {
                    "category": "ecommerce",
                    "subcategory": "fashion_and_lifestyle",
                    "addresses": {
                        "registered": {
                            "street": "Business Address",
                            "city": "Bangalore",
                            "state": "Karnataka",
                            "postal_code": "560001",
                            "country": "IN"
                        }
                    }
                },
                "legal_info": {
                    "pan": "",  # Will be updated after KYC
                    "gst": ""   # Optional GST number
                }
            }
            
            # Create linked account via Razorpay API
            account = self.client.account.create(account_data)
            
            # Update vendor with Razorpay account details
            vendor.razorpay_account_id = account['id']
            vendor.razorpay_linked_account_status = account.get('status', 'created')
            vendor.save()
            
            logger.info(f"Created Razorpay linked account {account['id']} for vendor {vendor.vendor_id}")
            return account
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Failed to create linked account for vendor {vendor.vendor_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating linked account: {str(e)}")
            raise
    
    def update_linked_account(self, vendor: VendorAccount, kyc_data: dict):
        """
        Update linked account with KYC information
        
        Args:
            vendor: VendorAccount instance
            kyc_data: Dictionary containing KYC details (PAN, GST, etc.)
                Example: {"pan": "ABCDE1234F", "gst": "29ABCDE1234F1Z5"}
            
        Returns:
            dict: Updated account details
            
        Raises:
            ValueError: If vendor doesn't have a Razorpay account
            razorpay.errors.BadRequestError: If update fails
        """
        try:
            if not vendor.razorpay_account_id:
                raise ValueError("Vendor does not have a Razorpay account")
            
            update_data = {
                "legal_info": kyc_data
            }
            
            # Update account via Razorpay API
            account = self.client.account.edit(
                vendor.razorpay_account_id, 
                update_data
            )
            
            vendor.razorpay_linked_account_status = account.get('status', 'updated')
            vendor.save()
            
            logger.info(f"Updated Razorpay account {vendor.razorpay_account_id} with KYC data")
            return account
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Failed to update linked account: {str(e)}")
            raise
    
    def create_transfer(self, order, vendor: VendorAccount, amount: float):
        """
        Transfer funds to vendor account after commission deduction
        
        Args:
            order: Order instance (must have razorpay_payment_id)
            vendor: VendorAccount instance
            amount: Amount to transfer in INR (vendor_settlement_amount)
            
        Returns:
            dict: Transfer details from Razorpay
            
        Raises:
            ValueError: If preconditions not met
            razorpay.errors.BadRequestError: If transfer fails
        """
        try:
            # Validation
            if not vendor.razorpay_account_id:
                raise ValueError("Vendor does not have a linked Razorpay account")
            
            if not order.razorpay_payment_id:
                raise ValueError("Order payment not completed - no payment ID")
            
            # Prepare transfer data
            transfer_data = {
                "account": vendor.razorpay_account_id,
                "amount": int(amount * 100),  # Convert to paise
                "currency": "INR",
                "notes": {
                    "order_id": str(order.order_id),
                    "vendor_id": str(vendor.vendor_id),
                    "commission": str(order.commission_amount),
                    "order_total": str(order.total_price)
                }
            }
            
            # Create transfer via Razorpay Route API
            transfer = self.client.payment.transfer(
                order.razorpay_payment_id,
                transfer_data
            )
            
            logger.info(f"Created transfer {transfer['id']} of ₹{amount} for order {order.order_id}")
            return transfer
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Failed to create transfer for order {order.order_id}: {str(e)}")
            raise
    
    def get_transfer_status(self, transfer_id: str):
        """
        Check status of a transfer
        
        Args:
            transfer_id: Razorpay transfer ID
            
        Returns:
            dict: Transfer status details
        """
        try:
            transfer = self.client.transfer.fetch(transfer_id)
            logger.info(f"Fetched transfer status: {transfer['id']} - {transfer.get('status')}")
            return transfer
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Failed to fetch transfer status for {transfer_id}: {str(e)}")
            raise
    
    def reverse_transfer(self, transfer_id: str, amount: float = None):
        """
        Reverse a transfer (for refunds/cancellations)
        
        Args:
            transfer_id: Razorpay transfer ID
            amount: Amount to reverse in INR (None for full reversal)
            
        Returns:
            dict: Reversal details
        """
        try:
            reversal_data = {}
            if amount:
                reversal_data['amount'] = int(amount * 100)  # Convert to paise
            
            reversal = self.client.transfer.reverse(transfer_id, reversal_data)
            
            logger.info(f"Reversed transfer {transfer_id}, amount: {amount or 'full'}")
            return reversal
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Failed to reverse transfer {transfer_id}: {str(e)}")
            raise
    
    def get_linked_account_balance(self, account_id: str):
        """
        Get balance of a linked account
        
        Args:
            account_id: Razorpay account ID
            
        Returns:
            dict: Balance details
        """
        try:
            balance = self.client.account.fetch(account_id)
            return balance
        except Exception as e:
            logger.error(f"Failed to fetch balance for account {account_id}: {str(e)}")
            raise
