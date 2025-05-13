import random
from django.core.mail import send_mail
from django.conf import settings
# from twilio.rest import Client
from .models import OTP
from .models import AdminNotification


def generate_otp():
    """Generate a 6-digit OTP."""
    return str(random.randint(100000, 999999))

def store_otp(identifier, otp):
    """Store OTP in the database with a 5-minute expiry."""
    OTP.objects.filter(identifier=identifier).delete()  # Remove old OTP if exists
    OTP.objects.create(identifier=identifier, otp_code=otp)

def verify_otp(identifier, otp):
    """Verify OTP from database."""
    try:
        otp_entry = OTP.objects.get(identifier=identifier, otp_code=otp)
        if otp_entry.is_expired():
            otp_entry.delete()  # Remove expired OTP
            return False
        otp_entry.delete()  # Remove OTP after successful verification
        return True
    except OTP.DoesNotExist:
        return False

def send_otp_email(email, otp):
    """Send OTP via email."""
    subject = "Your OTP Code to login to T-Stocks"
    message = f"Your OTP code is: {otp}. It expires in 5 minutes."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
    
#admin notification
def notify_admins(title, message):
    AdminNotification.objects.create(title=title, message=message)

# def send_otp_sms(phone_number, otp):
#     """Send OTP via SMS using Twilio."""
#     client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#     message = client.messages.create(
#         body=f"Your OTP code is: {otp}",
#         from_=settings.TWILIO_PHONE_NUMBER,
#         to=phone_number
#     )
#     return message.sid

def create_admin_notification(user,title, message, event_type=None):
    AdminNotification.objects.create(
        title=title,
        user=user,
        message=message,
        event_type=event_type
    )  