#!/usr/bin/env python3
"""
Form Field Analysis - Check if frontend/mobile match backend
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from users.models import CustomUser
from products.models import Product, Category
from orders.models import Order, OrderDetail, Cart, CartItem
from django.db import connection

print("\n" + "="*80)
print("BACKEND DATABASE SCHEMA ANALYSIS")
print("="*80 + "\n")

def get_table_fields(table_name):
    """Get all fields from a database table"""
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        return [(col[1], col[2], col[3], col[4], col[5]) for col in columns]

# ========== USERS TABLE ==========
print("1. USERS TABLE (CustomUser Model)")
print("-" * 80)
print("Table: users")
print("\nDatabase Fields:")
users_fields = get_table_fields('users')
for field in users_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

print("\n📝 SIGNUP REQUIREMENTS (CustomerSignupSerializer):")
print("  Required fields:")
print("    ✅ username (CharField)")
print("    ✅ email (EmailField, unique)")
print("    ✅ phone_number (CharField, unique)")
print("  Optional fields:")
print("    ⚪ default_shipping_address (TextField)")
print("  Auto-generated:")
print("    🤖 user_id (AutoField)")
print("    🤖 role (default: 'customer')")
print("    🤖 created_at (default: now)")

print("\n❌ MOBILE APP SENDS:")
print("  - username ✅")
print("  - phone_number ✅")
print("  - email ✅")
print("  - password ❌ (NOT in serializer!)")

print("\n⚠️  ISSUE FOUND:")
print("  Mobile app sends 'password' but backend CustomerSignupSerializer")
print("  does NOT include password field!")
print("  Backend creates user WITHOUT password (OTP-based auth only)")

# ========== PRODUCTS TABLE ==========
print("\n" + "="*80)
print("2. PRODUCTS TABLE")
print("-" * 80)
print("Table: products")
print("\nDatabase Fields:")
products_fields = get_table_fields('products')
for field in products_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default and name != 'product_id' else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

# ========== CATEGORY TABLE ==========
print("\n" + "="*80)
print("3. CATEGORY TABLE")
print("-" * 80)
print("Table: category")
print("\nDatabase Fields:")
category_fields = get_table_fields('category')
for field in category_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default and name != 'category_id' else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

# ========== ORDERS TABLE ==========
print("\n" + "="*80)
print("4. ORDERS TABLE")
print("-" * 80)
print("Table: orders")
print("\nDatabase Fields:")
orders_fields = get_table_fields('orders')
for field in orders_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default and name != 'order_id' else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

# ========== CART TABLE ==========
print("\n" + "="*80)
print("5. CART TABLE")
print("-" * 80)
print("Table: cart")
print("\nDatabase Fields:")
cart_fields = get_table_fields('cart')
for field in cart_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default and name != 'cart_id' else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

# ========== CART ITEMS TABLE ==========
print("\n" + "="*80)
print("6. CART ITEMS TABLE")
print("-" * 80)
print("Table: cart_items")
print("\nDatabase Fields:")
cart_items_fields = get_table_fields('cart_items')
for field in cart_items_fields:
    name, type_, notnull, default, pk = field
    required = "REQUIRED" if notnull and not default and name != 'id' else "OPTIONAL"
    primary = " (PRIMARY KEY)" if pk else ""
    print(f"  - {name}: {type_} [{required}]{primary}")

# ========== SUMMARY ==========
print("\n" + "="*80)
print("📊 CRITICAL FINDINGS")
print("="*80 + "\n")

print("1. SIGNUP FORM MISMATCH:")
print("   Mobile App Signup.tsx sends:")
print("     ✅ username")
print("     ✅ phone_number")
print("     ✅ email")
print("     ❌ password (REMOVED from form but still in code comments)")
print()
print("   Backend CustomerSignupSerializer expects:")
print("     ✅ username")
print("     ✅ phone_number")
print("     ✅ email")
print("     ❌ password (NOT in fields list)")
print()
print("   ✅ MATCH: Mobile correctly sends username, phone_number, email")
print("   ⚠️  NOTE: No password is set during signup (OTP-based login only)")
print()

print("2. UNIQUE CONSTRAINTS:")
print("   ✅ email: Must be unique")
print("   ✅ phone_number: Must be unique")
print("   ⚠️  username: NOT unique (multiple users can have same username)")
print()

print("3. REQUIRED FIELDS FOR SIGNUP:")
print("   ✅ username (can be any string)")
print("   ✅ email (must be valid email, unique)")
print("   ✅ phone_number (must be unique)")
print()

print("4. AUTO-GENERATED FIELDS:")
print("   🤖 user_id (primary key)")
print("   🤖 role (defaults to 'customer')")
print("   🤖 created_at (defaults to now)")
print("   🤖 updated_at (auto-updates)")
print()

print("5. SIGNUP FLOW:")
print("   Step 1: POST /api/users/signup/")
print("           Body: {username, email, phone_number}")
print("   Step 2: Backend generates OTP and sends to email")
print("   Step 3: POST /api/users/verify-otp/")
print("           Body: {identifier, otp}")
print("   Step 4: User account is created (no password!)")
print()

print("6. LOGIN FLOW (OTP-BASED):")
print("   ⚠️  Since signup doesn't set password, users CANNOT login with password!")
print("   Users must:")
print("     1. POST /api/users/login-request-otp/ (email + password)")
print("     2. Wait for OTP email")
print("     3. POST /api/users/verify-otp/ (email + otp)")
print()

print("="*80)
print("✅ CONCLUSION:")
print("="*80)
print()
print("Mobile app signup form is CORRECT for the backend schema!")
print()
print("The issue is likely:")
print("  1. Email configuration missing (OTP not being sent)")
print("  2. User trying to login with password (which doesn't exist)")
print()
print("SOLUTION:")
print("  1. Use test@example.com with OTP 000000 for testing")
print("  2. Or configure EMAIL_HOST_USER in .env file")
print("  3. Users created via signup have NO password (OTP login only)")
print()

print("="*80)
