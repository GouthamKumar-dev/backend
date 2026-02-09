import random
from django.core.mail import send_mail
from django.conf import settings
from smtplib import SMTPRecipientsRefused, SMTPAuthenticationError
from django.core.mail import get_connection, EmailMessage
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
    """Send OTP via email and handle rate-limiting errors."""
    subject = "Your OTP Code to login to T-Stocks"
    message = f"Your OTP code is: {otp}. It expires in 5 minutes."
    
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        return True  # Email sent successfully

    except SMTPAuthenticationError as e:
        # Authentication failed (bad credentials). In development, fall back to console backend
        # so developers can still see OTPs. In production, return False to signal failure.
        print(f"ERROR: SMTP authentication failed: {e}")
        if settings.DEBUG:
            try:
                conn = get_connection('django.core.mail.backends.console.EmailBackend')
                EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, [email], connection=conn).send()
                print("INFO: Fallback to console email backend used (DEBUG=True). OTP printed to console.)")
                return True
            except Exception as e2:
                print(f"ERROR: Fallback to console backend also failed: {e2}")
                return False
        return False

    except SMTPRecipientsRefused as e:
        # Recipient refused (rate limit or invalid recipient)
        print(f"ERROR: Recipient rate limited or refused: {e}")
        # The calling view must check for 'False' and return a 429 status.
        return False

    except Exception as e:
        # Catch other errors (Connection Refused, timeout, etc.).
        # If we're in DEBUG and the error looks like an auth/bad-credentials issue,
        # fall back to the console backend so developers can continue.
        err_text = str(e)
        print(f"ERROR: An unknown email error occurred: {err_text}")
        if settings.DEBUG and ("535" in err_text or "BadCredentials" in err_text or "authentication" in err_text.lower()):
            try:
                conn = get_connection('django.core.mail.backends.console.EmailBackend')
                EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, [email], connection=conn).send()
                print("INFO: Fallback to console email backend used (DEBUG=True). OTP printed to console.)")
                return True
            except Exception as e2:
                print(f"ERROR: Fallback to console backend also failed: {e2}")
                return False
        return False
    
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