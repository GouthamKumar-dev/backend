#!/usr/bin/env python3
"""
Razorpay Webhook Signature Test Script
Tests HMAC-SHA256 signature verification for Razorpay webhooks
"""

import hmac
import hashlib
import json
import requests

# Configuration
WEBHOOK_URL = "http://localhost:8000/api/orders/razorpay-webhook/"
WEBHOOK_SECRET = "helmstone123"

# Test payload (simulates Razorpay webhook)
test_payload = {
    "event": "payment.captured",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test_123456",
                "order_id": "order_test_789",
                "status": "captured",
                "amount": 50000,  # 500.00 INR (in paise)
                "currency": "INR",
                "method": "card",
                "email": "test@example.com",
                "contact": "+919876543210"
            }
        }
    }
}

def generate_signature(payload_dict, secret):
    """Generate HMAC-SHA256 signature for webhook payload"""
    payload_string = json.dumps(payload_dict)
    payload_bytes = payload_string.encode('utf-8')
    secret_bytes = secret.encode('utf-8')
    
    signature = hmac.new(
        secret_bytes,
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return signature

def test_webhook(url, payload, secret):
    """Test webhook endpoint with valid signature"""
    print("=" * 70)
    print("RAZORPAY WEBHOOK SIGNATURE TEST")
    print("=" * 70)
    
    # Generate signature
    signature = generate_signature(payload, secret)
    print(f"\n✓ Generated Signature: {signature}")
    
    # Prepare request
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature
    }
    
    payload_json = json.dumps(payload)
    print(f"\n✓ Payload:\n{json.dumps(payload, indent=2)}")
    
    # Send request
    print(f"\n✓ Sending POST request to: {url}")
    try:
        response = requests.post(url, headers=headers, data=payload_json)
        
        print(f"\n📊 Response:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Body: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Webhook processed successfully!")
        else:
            print(f"\n❌ FAILED: Unexpected status code {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to server.")
        print("   Make sure Django is running: python manage.py runserver")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

def test_invalid_signature(url, payload):
    """Test webhook endpoint with invalid signature"""
    print("\n" + "=" * 70)
    print("TESTING INVALID SIGNATURE (Should Fail)")
    print("=" * 70)
    
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": "invalid_signature_12345"
    }
    
    payload_json = json.dumps(payload)
    
    try:
        response = requests.post(url, headers=headers, data=payload_json)
        
        print(f"\n📊 Response:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Body: {response.text}")
        
        if response.status_code == 400:
            print("\n✅ GOOD: Invalid signature correctly rejected!")
        else:
            print(f"\n⚠️  WARNING: Expected 400, got {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to server.")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

def main():
    print("\n🔐 Razorpay Webhook Signature Test")
    print(f"📍 Target URL: {WEBHOOK_URL}")
    print(f"🔑 Webhook Secret: {WEBHOOK_SECRET}\n")
    
    # Test valid signature
    test_webhook(WEBHOOK_URL, test_payload, WEBHOOK_SECRET)
    
    # Test invalid signature
    test_invalid_signature(WEBHOOK_URL, test_payload)
    
    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
