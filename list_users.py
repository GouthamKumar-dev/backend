import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from users.models import CustomUser

print("\n" + "="*60)
print("DATABASE USERS LIST")
print("="*60 + "\n")

users = CustomUser.objects.all()

if users.count() == 0:
    print("❌ No users found in database!\n")
else:
    print(f"✅ Found {users.count()} user(s):\n")
    
    for i, user in enumerate(users, 1):
        print(f"{i}. {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Phone: {user.phone_number}")
        print(f"   Role: {user.role}")
        print(f"   Is Staff: {user.is_staff}")
        print(f"   Is Superuser: {user.is_superuser}")
        print(f"   Is Active: {user.is_active}")
        print()

print("="*60)
print("\nTo test login, you can use:")
print("  Email: admin@upstocks.com")
print("  Password: admin123")
print("\nNote: Email OTP will NOT work without EMAIL_HOST_USER and EMAIL_HOST_PASSWORD")
print("      in .env file. Use test@example.com with OTP: 000000 for testing.\n")
