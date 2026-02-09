"""
Data Migration Script: Create Owner and Link Products to Admin
Run this after running migrations
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from users.models import CustomUser, UserRole
from products.models import Product
from django.db import transaction

@transaction.atomic
def setup_owner_and_link_products():
    print("=" * 60)
    print("Setting up Platform Owner and linking products to admin...")
    print("=" * 60)
    
    # Step 1: Create platform owner account
    print("\n1. Creating Platform Owner account...")
    owner, created = CustomUser.objects.get_or_create(
        email='pingwgc@gmail.com',
        defaults={
            'username': 'Platform Owner',
            'phone_number': '9876543210',  # Unique phone number for owner
            'role': UserRole.OWNER
        }
    )
    
    if created:
        owner.set_password('owner123')  # Change this to a secure password!
        owner.save()
        print(f"   ✅ Owner created: {owner.email}")
        print(f"   📧 Email: {owner.email}")
        print(f"   🔑 Password: owner123 (CHANGE THIS!)")
    else:
        print(f"   ℹ️  Owner already exists: {owner.email}")
    
    # Step 2: Get or create first admin user
    print("\n2. Finding or creating admin user...")
    admin = CustomUser.objects.filter(role=UserRole.ADMIN).first()
    
    if not admin:
        print("   No admin found. Creating default admin...")
        admin = CustomUser.objects.create_user(
            username='Default Admin',
            email='admin@tstocks.com',
            phone_number='8888888888',
            password='admin123',
            role=UserRole.ADMIN
        )
        print(f"   ✅ Admin created: {admin.email}")
        print(f"   📧 Email: admin@tstocks.com")
        print(f"   🔑 Password: admin123 (CHANGE THIS!)")
    else:
        print(f"   ✅ Using existing admin: {admin.email}")
    
    # Step 3: Link all products to this admin
    print("\n3. Linking products to admin...")
    unlinked_products = Product.objects.filter(admin__isnull=True)
    count = unlinked_products.count()
    
    if count > 0:
        unlinked_products.update(admin=admin)
        print(f"   ✅ Linked {count} products to {admin.username}")
    else:
        print("   ℹ️  All products already linked to admins")
    
    # Step 4: Summary
    print("\n" + "=" * 60)
    print("SETUP COMPLETE!")
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"   • Platform Owner: {owner.email}")
    print(f"   • Admin Count: {CustomUser.objects.filter(role=UserRole.ADMIN).count()}")
    print(f"   • Total Products: {Product.objects.count()}")
    print(f"   • Products linked to admins: {Product.objects.filter(admin__isnull=False).count()}")
    
    print(f"\n🔐 Login Credentials:")
    print(f"   Owner:")
    print(f"     Email: {owner.email}")
    print(f"     Password: owner123")
    print(f"   Admin:")
    print(f"     Email: {admin.email}")
    print(f"     Password: (use existing or reset)")
    
    print(f"\n⚠️  IMPORTANT: Change default passwords immediately!")
    print("=" * 60)

if __name__ == "__main__":
    setup_owner_and_link_products()
