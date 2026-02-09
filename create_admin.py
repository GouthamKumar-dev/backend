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
        phone_number='9574586985',
        username='Goutham',
        email='gouthamkumar091@gmail.com',
        password='Admin@123'
    )
    print('Admin user created successfully!')
    print(f'Email: gouthamkumar091@gmail.com')
    print(f'Username: Goutham')
    print(f'Password: Admin@123')
    print(f'Phone: 9574586985')
    print(f'Role: {admin.role}')
