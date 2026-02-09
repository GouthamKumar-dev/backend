"""
QuickEKYC Service
Handles integration with QuickEKYC.com API for automated KYC verification.

Documentation: https://quickekyc.com/api-docs
"""

import requests
import json
import logging
from django.conf import settings
from typing import Dict, Optional, Tuple
from .models import KYCVerification, VendorAccount

logger = logging.getLogger(__name__)


class QuickEKYCService:
    """
    Service class for QuickEKYC.com API integration.
    Handles Aadhaar, PAN, and GST verification.
    """

    BASE_URL = "https://api.quickekyc.com/v1"
    
    def __init__(self):
        """Initialize QuickEKYC service with API credentials."""
        self.api_key = getattr(settings, 'QUICKEKYC_API_KEY', '')
        self.api_secret = getattr(settings, 'QUICKEKYC_API_SECRET', '')
        
        if not self.api_key or not self.api_secret:
            logger.warning("QuickEKYC credentials not configured in settings")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'X-API-Secret': self.api_secret
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """
        Make HTTP request to QuickEKYC API.
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path
            data: Request payload
            
        Returns:
            Tuple of (success, response_data)
        """
        url = f"{self.BASE_URL}/{endpoint}"
        headers = self._get_headers()
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=data, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return True, response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"QuickEKYC API HTTP error: {e}")
            error_data = {}
            try:
                error_data = e.response.json()
            except:
                error_data = {'error': str(e)}
            return False, error_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"QuickEKYC API request error: {e}")
            return False, {'error': str(e)}
    
    def verify_aadhaar(self, aadhaar_number: str, name: str) -> Tuple[bool, Dict]:
        """
        Initiate Aadhaar verification via QuickEKYC.
        
        Args:
            aadhaar_number: 12-digit Aadhaar number
            name: Name to verify against Aadhaar
            
        Returns:
            Tuple of (success, verification_data)
            
        Response format:
        {
            "verification_id": "qekyc_xxx",
            "status": "pending|verified|failed",
            "name_match": true/false,
            "aadhaar_details": {
                "name": "John Doe",
                "dob": "1990-01-01",
                "address": "...",
                "photo_url": "..."
            }
        }
        """
        # Remove spaces and validate
        aadhaar_number = aadhaar_number.replace(" ", "").replace("-", "")
        if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
            return False, {'error': 'Invalid Aadhaar number format'}
        
        data = {
            'document_type': 'aadhaar',
            'document_number': aadhaar_number,
            'name': name,
            'verify_name': True
        }
        
        success, response = self._make_request('POST', 'verify/aadhaar', data)
        
        if success:
            logger.info(f"Aadhaar verification initiated: {response.get('verification_id')}")
        else:
            logger.error(f"Aadhaar verification failed: {response}")
        
        return success, response
    
    def verify_pan(self, pan_number: str, name: str) -> Tuple[bool, Dict]:
        """
        Verify PAN card via QuickEKYC.
        
        Args:
            pan_number: 10-character PAN number
            name: Name to verify against PAN
            
        Returns:
            Tuple of (success, verification_data)
            
        Response format:
        {
            "verification_id": "qekyc_xxx",
            "status": "verified|failed",
            "name_match": true/false,
            "pan_details": {
                "name": "John Doe",
                "pan_number": "ABCDE1234F",
                "category": "Individual",
                "status": "Active"
            }
        }
        """
        # Validate PAN format
        pan_number = pan_number.upper().replace(" ", "")
        if len(pan_number) != 10:
            return False, {'error': 'Invalid PAN number format'}
        
        data = {
            'document_type': 'pan',
            'document_number': pan_number,
            'name': name,
            'verify_name': True
        }
        
        success, response = self._make_request('POST', 'verify/pan', data)
        
        if success:
            logger.info(f"PAN verification completed: {response.get('verification_id')}")
        else:
            logger.error(f"PAN verification failed: {response}")
        
        return success, response
    
    def verify_gst(self, gstin: str, business_name: str) -> Tuple[bool, Dict]:
        """
        Verify GST number via QuickEKYC.
        
        Args:
            gstin: 15-character GSTIN
            business_name: Business name to verify
            
        Returns:
            Tuple of (success, verification_data)
            
        Response format:
        {
            "verification_id": "qekyc_xxx",
            "status": "verified|failed",
            "name_match": true/false,
            "gst_details": {
                "legal_name": "ABC Pvt Ltd",
                "trade_name": "ABC Electronics",
                "gstin": "27AABCU9603R1ZM",
                "status": "Active",
                "registration_date": "2017-07-01",
                "address": "...",
                "business_type": "Retailer"
            }
        }
        """
        # Validate GSTIN format
        gstin = gstin.upper().replace(" ", "")
        if len(gstin) != 15:
            return False, {'error': 'Invalid GSTIN format'}
        
        data = {
            'document_type': 'gst',
            'document_number': gstin,
            'business_name': business_name,
            'verify_name': True
        }
        
        success, response = self._make_request('POST', 'verify/gst', data)
        
        if success:
            logger.info(f"GST verification completed: {response.get('verification_id')}")
        else:
            logger.error(f"GST verification failed: {response}")
        
        return success, response
    
    def verify_bank_account(self, account_number: str, ifsc_code: str, 
                          account_holder_name: str) -> Tuple[bool, Dict]:
        """
        Verify bank account via QuickEKYC.
        
        Args:
            account_number: Bank account number
            ifsc_code: Bank IFSC code
            account_holder_name: Account holder name
            
        Returns:
            Tuple of (success, verification_data)
            
        Response format:
        {
            "verification_id": "qekyc_xxx",
            "status": "verified|failed",
            "name_match": true/false,
            "bank_details": {
                "account_number": "1234567890",
                "ifsc": "SBIN0001234",
                "account_holder_name": "John Doe",
                "bank_name": "State Bank of India",
                "branch": "Main Branch",
                "account_type": "Savings",
                "account_status": "Active"
            }
        }
        """
        data = {
            'document_type': 'bank_account',
            'account_number': account_number,
            'ifsc_code': ifsc_code.upper(),
            'account_holder_name': account_holder_name,
            'verify_name': True
        }
        
        success, response = self._make_request('POST', 'verify/bank', data)
        
        if success:
            logger.info(f"Bank account verification completed: {response.get('verification_id')}")
        else:
            logger.error(f"Bank account verification failed: {response}")
        
        return success, response
    
    def get_verification_status(self, verification_id: str) -> Tuple[bool, Dict]:
        """
        Check status of ongoing verification.
        
        Args:
            verification_id: QuickEKYC verification ID
            
        Returns:
            Tuple of (success, verification_data)
        """
        success, response = self._make_request('GET', f'verify/status/{verification_id}')
        
        if success:
            logger.info(f"Retrieved verification status: {verification_id}")
        else:
            logger.error(f"Failed to get verification status: {verification_id}")
        
        return success, response
    
    def process_kyc_document(self, kyc_verification: KYCVerification) -> bool:
        """
        Process a KYC document through QuickEKYC API.
        
        Args:
            kyc_verification: KYCVerification model instance
            
        Returns:
            bool: True if verification initiated successfully
        """
        vendor = kyc_verification.vendor
        document_type = kyc_verification.document_type
        document_number = kyc_verification.document_number
        
        # Get appropriate name based on document type
        if document_type in ['aadhaar', 'pan', 'bank_statement']:
            name = f"{vendor.user.first_name} {vendor.user.last_name}".strip()
            if not name:
                name = vendor.user.email.split('@')[0]
        else:
            name = vendor.business_name
        
        # Call appropriate verification method
        success = False
        response_data = {}
        
        try:
            if document_type == 'aadhaar':
                success, response_data = self.verify_aadhaar(document_number, name)
                
            elif document_type == 'pan':
                success, response_data = self.verify_pan(document_number, name)
                
            elif document_type == 'gst_certificate':
                success, response_data = self.verify_gst(document_number, vendor.business_name)
                
            elif document_type == 'bank_statement':
                success, response_data = self.verify_bank_account(
                    vendor.bank_account_number,
                    vendor.bank_ifsc_code,
                    vendor.bank_account_holder_name
                )
            
            else:
                # For business_proof and other documents, mark for manual review
                kyc_verification.status = 'in_review'
                kyc_verification.save()
                logger.info(f"Document type {document_type} requires manual review")
                return True
            
            if success:
                # Update KYC record with verification ID
                verification_id = response_data.get('verification_id')
                kyc_verification.quickekyc_verification_id = verification_id
                
                # Update status based on response
                status = response_data.get('status', 'pending')
                if status == 'verified':
                    kyc_verification.status = 'verified'
                    kyc_verification.verification_data = response_data
                    
                    # Auto-approve if name matches
                    if response_data.get('name_match', False):
                        kyc_verification.status = 'verified'
                    else:
                        kyc_verification.status = 'in_review'
                        kyc_verification.rejection_reason = "Name mismatch - requires manual review"
                        
                elif status == 'failed':
                    kyc_verification.status = 'rejected'
                    kyc_verification.rejection_reason = response_data.get('error', 'Verification failed')
                else:
                    kyc_verification.status = 'in_review'
                
                kyc_verification.save()
                return True
            else:
                # Verification API call failed
                kyc_verification.status = 'in_review'
                kyc_verification.rejection_reason = response_data.get('error', 'API verification failed')
                kyc_verification.save()
                return False
                
        except Exception as e:
            logger.error(f"Error processing KYC document: {e}")
            kyc_verification.status = 'in_review'
            kyc_verification.rejection_reason = f"Processing error: {str(e)}"
            kyc_verification.save()
            return False
    
    def handle_webhook(self, webhook_data: Dict) -> bool:
        """
        Handle webhook callback from QuickEKYC.
        
        Args:
            webhook_data: Webhook payload from QuickEKYC
            
        Webhook format:
        {
            "event": "verification.completed|verification.failed",
            "verification_id": "qekyc_xxx",
            "status": "verified|failed",
            "document_type": "aadhaar|pan|gst",
            "data": {...},
            "timestamp": "2026-01-24T10:00:00Z"
        }
        
        Returns:
            bool: True if webhook processed successfully
        """
        try:
            event = webhook_data.get('event')
            verification_id = webhook_data.get('verification_id')
            status = webhook_data.get('status')
            data = webhook_data.get('data', {})
            
            if not verification_id:
                logger.error("Webhook missing verification_id")
                return False
            
            # Find KYC record
            try:
                kyc = KYCVerification.objects.get(quickekyc_verification_id=verification_id)
            except KYCVerification.DoesNotExist:
                logger.error(f"KYC record not found for verification_id: {verification_id}")
                return False
            
            # Update KYC status based on webhook event
            if event == 'verification.completed' and status == 'verified':
                kyc.status = 'verified'
                kyc.verification_data = data
                
                # Check name match
                if not data.get('name_match', False):
                    kyc.status = 'in_review'
                    kyc.rejection_reason = "Name mismatch - requires manual review"
                    
            elif event == 'verification.failed' or status == 'failed':
                kyc.status = 'rejected'
                kyc.rejection_reason = data.get('error', 'Verification failed')
            
            kyc.save()
            
            # Check if all KYC documents are verified for vendor
            vendor = kyc.vendor
            all_verified = self._check_vendor_kyc_complete(vendor)
            
            if all_verified:
                vendor.kyc_verified = True
                vendor.save()
                logger.info(f"Vendor {vendor.vendor_id} KYC fully verified")
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling QuickEKYC webhook: {e}")
            return False
    
    def _check_vendor_kyc_complete(self, vendor: VendorAccount) -> bool:
        """
        Check if vendor has all required KYC documents verified.
        
        Required documents:
        - Aadhaar OR PAN (at least one)
        - Bank Statement
        - GST Certificate (if business)
        
        Args:
            vendor: VendorAccount instance
            
        Returns:
            bool: True if all required documents verified
        """
        kyc_docs = KYCVerification.objects.filter(vendor=vendor)
        
        # Check for at least one ID proof
        has_id_proof = kyc_docs.filter(
            document_type__in=['aadhaar', 'pan'],
            status='verified'
        ).exists()
        
        # Check for bank statement
        has_bank = kyc_docs.filter(
            document_type='bank_statement',
            status='verified'
        ).exists()
        
        # GST is optional for small businesses
        # But if submitted, must be verified
        gst_docs = kyc_docs.filter(document_type='gst_certificate')
        gst_verified = True
        if gst_docs.exists():
            gst_verified = gst_docs.filter(status='verified').exists()
        
        return has_id_proof and has_bank and gst_verified
