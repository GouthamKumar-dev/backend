#!/usr/bin/env python3
"""
Test Login Flow
Tests the 2-step OTP login process
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8000/api"

def test_login():
    print("\n" + "="*70)
    print("🔐 TESTING T-STOCKS LOGIN FLOW")
    print("="*70 + "\n")

    # Test 1: Login with test account
    print("📧 Step 1: Requesting OTP for test@example.com...")
    print("-" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/users/login-request-otp/",
            json={
                "email": "test@example.com",
                "password": "test123"
            },
            timeout=5
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("   ✅ OTP request successful!\n")
        else:
            print("   ❌ OTP request failed!\n")
            return False
            
    except requests.exceptions.ConnectionError:
        print("   ❌ ERROR: Cannot connect to backend!")
        print("   Make sure backend is running on http://localhost:8000")
        return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False

    # Test 2: Verify OTP
    print("🔑 Step 2: Verifying OTP...")
    print("-" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/users/verify-otp/",
            json={
                "identifier": "test@example.com",
                "otp": "000000"
            },
            timeout=5
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            tokens = response.json()
            print("   ✅ Login successful! Got JWT tokens:\n")
            print(f"   Access Token:  {tokens.get('access', 'N/A')[:60]}...")
            print(f"   Refresh Token: {tokens.get('refresh', 'N/A')[:60]}...")
            print(f"\n   User Info:")
            print(f"   - ID: {tokens.get('user', {}).get('user_id', 'N/A')}")
            print(f"   - Email: {tokens.get('user', {}).get('email', 'N/A')}")
            print(f"   - Username: {tokens.get('user', {}).get('username', 'N/A')}")
            print(f"   - Role: {tokens.get('user', {}).get('role', 'N/A')}")
            return True
        else:
            print(f"   ❌ Verification failed!")
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False

def test_your_account():
    print("\n" + "="*70)
    print("🔐 TESTING YOUR ACCOUNT (gouthamkumar091@gmail.com)")
    print("="*70 + "\n")
    
    password = input("Enter your password: ")
    
    print("\n📧 Step 1: Requesting OTP...")
    print("-" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/users/login-request-otp/",
            json={
                "email": "gouthamkumar091@gmail.com",
                "password": password
            },
            timeout=5
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n   ✅ OTP request successful!")
            print("\n   ⚠️  NOTE: Email won't be sent (no EMAIL_HOST_USER configured)")
            print("   You need to check the database for the OTP code.\n")
            
            print("   Run this to get your OTP:")
            print("   " + "-" * 66)
            print("   python -c \"import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings'); django.setup(); from users.models import OTP; otp = OTP.objects.filter(identifier='gouthamkumar091@gmail.com').first(); print(f'OTP: {otp.otp_code}' if otp else 'No OTP found')\"")
            print("   " + "-" * 66)
            
        else:
            print("   ❌ Failed!")
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

if __name__ == "__main__":
    print("\n🚀 T-Stocks Login Test Suite")
    print("=" * 70)
    
    while True:
        print("\nSelect test:")
        print("1. Test with test@example.com (works without email)")
        print("2. Test with your account (gouthamkumar091@gmail.com)")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            success = test_login()
            if success:
                print("\n" + "="*70)
                print("✅ ALL TESTS PASSED!")
                print("="*70)
                print("\nYou can now use these credentials in your frontend/mobile app:")
                print("  Email: test@example.com")
                print("  Password: test123")
                print("  OTP: 000000")
                print("="*70 + "\n")
        elif choice == "2":
            test_your_account()
        elif choice == "3":
            print("\n👋 Goodbye!\n")
            break
        else:
            print("❌ Invalid choice!")
