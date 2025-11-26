import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from users.models import CustomUser

# Check if admin already exists
if CustomUser.objects.filter(email='admin@upstocks.com').exists():
    print('Admin user already exists!')
    admin = CustomUser.objects.get(email='admin@upstocks.com')
    print(f'Email: {admin.email}')
    print(f'Username: {admin.username}')
    print(f'Phone: {admin.phone_number}')
    print(f'Role: {admin.role}')
else:
    # Create admin user
    admin = CustomUser.objects.create_superuser(
        phone_number='1234567890',
        username='admin',
        email='admin@upstocks.com',
        password='admin123'
    )
    print('Admin user created successfully!')
    print(f'Email: admin@upstocks.com')
    print(f'Username: admin')
    print(f'Password: admin123')
    print(f'Phone: 1234567890')
    print(f'Role: {admin.role}')
