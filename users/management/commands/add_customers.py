from django.core.management.base import BaseCommand
from users.models import CustomUser, UserRole


class Command(BaseCommand):
    help = 'Add 1 customer account to the database'

    def handle(self, *args, **options):
        customers = [
            {
                'email': 'test@gmail.com',
                'username': 'Test',
                'phone_number': '9876543210',
            },
        ]

        password = 'Abcd@123'
        created_count = 0
        skipped_count = 0

        for customer_data in customers:
            # Check if user already exists
            if CustomUser.objects.filter(email=customer_data['email']).exists():
                self.stdout.write(
                    self.style.WARNING(f"Customer {customer_data['email']} already exists. Skipping.")
                )
                skipped_count += 1
                continue

            # Create the customer
            try:
                user = CustomUser.objects.create_user(
                    email=customer_data['email'],
                    username=customer_data['username'],
                    phone_number=customer_data['phone_number'],
                    password=password,
                    role=UserRole.CUSTOMER,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully created customer: {customer_data['email']}")
                )
                created_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to create {customer_data['email']}: {str(e)}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"\n=== Summary ===\nCreated: {created_count}\nSkipped: {skipped_count}")
        )
