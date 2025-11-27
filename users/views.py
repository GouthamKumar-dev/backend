# views.py
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes, action
from .models import CustomUser ,UserRole
from .serializers import UserSerializer,CustomTokenObtainPairSerializer,CustomTokenRefreshSerializer, LoginSerializer, CreateUserSerializer,OTPVerifySerializer, ResetPasswordSerializer, LoginWithEmailSerializer,CustomerSignupSerializer
from .permissions import IsAdminUser, IsStaffUser, IsAdminOrStaff
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.pagination import PageNumberPagination

from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response

from django.contrib.auth import authenticate
from rest_framework import status
from ecommerce.logger import logger 
from .utils import generate_otp, store_otp, send_otp_email, verify_otp
from users.models import OTP, DeleteAccountOTP
from django.utils import timezone 
from .utils import create_admin_notification
from .models import AdminNotification
from .serializers import AdminNotificationSerializer

class CustomRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token['user_id'] = user.user_id  # Add custom user_id claim
        return token
    
class UserPagination(PageNumberPagination):
    page_size = 10  # Number of items per page (change as needed)
    page_size_query_param = 'page_size'  # Allows clients to set page size dynamically
    max_page_size = 100  # Prevents very large queries


class AdminNotificationListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """
        Retrieve all admin notifications (paginated) and mark only unread ones as read.
        """
        notifications = AdminNotification.objects.all().order_by("-created_at")

        # Use existing pagination class
        paginator = UserPagination()
        paginated_notifications = paginator.paginate_queryset(notifications, request)

        # Mark only unread ones in this page as read
        unread_ids = [n.id for n in paginated_notifications if not n.is_read]
        AdminNotification.objects.filter(id__in=unread_ids).update(is_read=True)

        serializer = AdminNotificationSerializer(paginated_notifications, many=True)
        return paginator.get_paginated_response(serializer.data)

class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerSignupSerializer(data=request.data)
        if serializer.is_valid():
        
            otp = generate_otp()
            email = serializer.validated_data.get("email")
            phone_number = serializer.validated_data.get("phone_number")

            identifier = email or phone_number

            # Save OTP and user data temporarily in the OTP model
            OTP.objects.update_or_create(
                identifier=identifier,
                defaults={
                    "otp_code": otp,
                    "user_data": serializer.validated_data,  # Temporarily store user data
                    "created_at": timezone.now(),
                },
            )

            # Send OTP via Email & SMS
            # --- START: ERROR HANDLING ADDED ---
            email_sent = send_otp_email(email, otp)
            if not email_sent:
                 # Clean up the temporary OTP entry if email sending failed due to rate limit
                OTP.objects.filter(identifier=identifier).delete() 
                return Response(
                    {"error": "Failed to send OTP. The recipient mailbox is temporarily restricted. Please wait 15 minutes and try again."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            # --- END: ERROR HANDLING ADDED ---
            # send_otp_sms(phone_number, otp)
            
            # Notify admins about new user signup
            create_admin_notification(user=None, title="New user signup", message=f"A new user has signed up with email: {email}", event_type="user_signup")

            return Response({"message": "OTP sent to email. Please verify to complete signup."}, 
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class LoginRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            password = serializer.validated_data["password"]
            user = authenticate(email=email, password=password)
            if user:
                otp = generate_otp()
                store_otp(user.phone_number, otp)
                store_otp(user.email, otp)

                # --- START: ERROR HANDLING ADDED ---
                email_sent = send_otp_email(user.email, otp)
                if not email_sent:
                    # Clean up the temporary OTP entry
                    OTP.objects.filter(identifier=user.email).delete() 
                    return Response(
                        {"error": "Failed to send OTP. The recipient mailbox is temporarily restricted. Please wait 15 minutes and try again."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
                # --- END: ERROR HANDLING ADDED ---
                # send_otp_sms(user.phone_number, otp)

                return Response({"message": "OTP sent to email"}, status=status.HTTP_200_OK)
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data["identifier"]
            otp = serializer.validated_data["otp"]
            otp_entry = OTP.objects.filter(identifier=identifier).first()

            # ------------------------------------------------------------------
            #                     GOOGLE PLAY REVIEW OTP BYPASS
            # ------------------------------------------------------------------
            # Allow Google Play testers to log in instantly with:
            # Email/Identifier → test@example.com
            # OTP              → 000000
            # ------------------------------------------------------------------
            if identifier == "hariii0811@gmail.com" and otp == "000000":
                user = CustomUser.objects.filter(email=identifier).first()

                # If test user does NOT exist, create it automatically
                if not user:
                    user = CustomUser.objects.create(
                        email="test@example.com",
                        username="playstoretester",
                        phone_number="0000000000",
                        role=UserRole.CUSTOMER,
                    )

                # Generate tokens for the test user
                refresh = RefreshToken.for_user(user)
                return Response({
                    "user": UserSerializer(user).data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }, status=status.HTTP_200_OK)
            # ------------------------------------------------------------------
            #                          END OF BYPASS
            # ------------------------------------------------------------------


            # NORMAL REAL OTP VALIDATION

            if otp_entry and otp_entry.otp_code == otp and not otp_entry.is_expired():
                # Check if user already exists
                user = CustomUser.objects.filter(email=identifier).first() or CustomUser.objects.filter(phone_number=identifier).first()

                if user:
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        "user": UserSerializer(user).data,
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    }, status=status.HTTP_200_OK)

                # Retrieve stored user data and create new user
                if otp_entry.user_data:
                    user_serializer = CustomerSignupSerializer(data=otp_entry.user_data)
                    if user_serializer.is_valid():
                        user = user_serializer.save()
                        refresh = RefreshToken.for_user(user)

                        # Delete OTP after successful verification
                        otp_entry.delete()

                        return Response({
                            "user": UserSerializer(user).data,
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                        }, status=status.HTTP_201_CREATED)
                    return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

                #----------
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        user = CustomUser.objects.filter(email=email).first()

        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure only Admins and Staff can request password reset
        if user.role not in [UserRole.ADMIN, UserRole.STAFF]:
            return Response({"error": "Your user role cannot perform this action."}, status=status.HTTP_403_FORBIDDEN)

        otp = generate_otp()
        store_otp(user.email, otp)
        store_otp(user.phone_number, otp)
        # --- START: ERROR HANDLING ADDED ---
        email_sent = send_otp_email(user.email, otp)
        if not email_sent:
            # Clean up the temporary OTP entry
            OTP.objects.filter(identifier=user.email).delete() 
            return Response(
                {"error": "Failed to send OTP. The recipient mailbox is temporarily restricted. Please wait 15 minutes and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        # --- END: ERROR HANDLING ADDED ---
        # send_otp_sms(user.phone_number, otp)

        return Response({"message": "OTP sent to reset password."}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            otp = serializer.validated_data["otp"]
            new_password = serializer.validated_data["new_password"]

            if not verify_otp(email, otp):
                return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.filter(email=email).first()

            if not user:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            # Ensure only Admins and Staff can reset passwords
            if user.role not in [UserRole.ADMIN, UserRole.STAFF]:
                return Response({"error": "Your user role cannot perform this action."}, status=status.HTTP_403_FORBIDDEN)

            user.set_password(new_password)
            user.save()
             # Notify admins about password reset
            create_admin_notification(user=user, title="Password reset", message=f"The password for user {user.email} has been reset.", event_type="password_reset")

            return Response({"message": "Password reset successful."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateUserView(APIView):
    """
    Allows Admins to create Admins, Staff, and Customers.
    Allows Staff to create only Staff and Customers.
    """
    permission_classes = [IsAuthenticated, IsAdminUser | IsStaffUser]

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User created successfully",
                "user": UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

# user view
# class UserViewSet(viewsets.ModelViewSet):
#     queryset = CustomUser.objects.all()
#     serializer_class = UserSerializer

#     def get_permissions(self):
#         if self.action in ['list', 'create']:
#             return [IsAdminUser()]
#         return [IsOwnerOrAdmin()]

class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_me(request):
    return Response({
        'phone_number': request.user.phone_number,
        'username': request.user.username,
        'email': request.user.email,
        'default_shipping_address' : request.user.default_shipping_address
    })

#logout view
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Log the incoming request data for debugging
            logger.debug(f"Request Data: {request.data}")

            # Extract the refresh token from the request data
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "'refresh' token is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Use the custom serializer for validation if required
            custom_serializer = CustomTokenRefreshSerializer(data={"refresh": refresh_token})
            if custom_serializer.is_valid():
                token = RefreshToken(refresh_token)
                token.blacklist()
                return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
            else:
                return Response(custom_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Log the error for debugging
            logger.error(f"Error during logout: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
# List all orders (paginated) for admins
class AdminUserListView(APIView):
    """
    Admin view to list all users.
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]  # Ensure only admins/staff can access
    pagination_class = UserPagination

    def get(self, request):
        """
        List all users.
        """
        users = CustomUser.objects.all().order_by("username")
        paginator = UserPagination()
        paginated_users = paginator.paginate_queryset(users, request)
        serializer = UserSerializer(paginated_users, many=True)

        return paginator.get_paginated_response(serializer.data)

class UpdateShippingAddressView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        """
        Allows users to update their default shipping address.
        """
        user = request.user
        new_address = request.data.get("default_shipping_address")

        if not new_address:
            return Response({"error": "Shipping address cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)

        user.default_shipping_address = new_address
        user.save()
         # Notify admins about address change
        create_admin_notification(user=user, title="User address update", message=f"The address for user {user.email} has been updated.", event_type="shipping_address_update")

        return Response({"message": "Shipping address updated successfully", "user": UserSerializer(user).data}, status=status.HTTP_200_OK)

# customer login using email and otp
class CustomerLoginRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginWithEmailSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]

            # Check if the user exists as a Customer
            customer_user = CustomUser.objects.filter(email=email, role=UserRole.CUSTOMER).first()
            
            # Check if the user exists as an Admin or Staff
            admin_or_staff_user = CustomUser.objects.filter(
                email=email, role__in=[UserRole.ADMIN, UserRole.STAFF]
            ).first()

            if admin_or_staff_user:
                return Response(
                    {"error": "Admins and Staff members cannot log in using OTP."},
                    status=status.HTTP_403_FORBIDDEN
                )

            if customer_user:
                otp = generate_otp()
                store_otp(customer_user.email, otp)
                # --- START: ERROR HANDLING ADDED ---
                email_sent = send_otp_email(customer_user.email, otp)
                if not email_sent:
                    # Clean up the temporary OTP entry
                    OTP.objects.filter(identifier=customer_user.email).delete()
                    return Response(
                        {"error": "Failed to send OTP. The recipient mailbox is temporarily restricted. Please wait 15 minutes and try again."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
                # --- END: ERROR HANDLING ADDED ---
                return Response({"message": "OTP sent to email."}, status=status.HTTP_200_OK)

            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteAccountRequestOTPView(APIView):
    """
    Request OTP for account deletion (customer only)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(email=email.lower(), role=UserRole.CUSTOMER)
        except CustomUser.DoesNotExist:
            return Response({"error": "Account not found."}, status=status.HTTP_404_NOT_FOUND)

        # Generate and send OTP
        otp = generate_otp()
        DeleteAccountOTP.objects.update_or_create(
            email=email.lower(),
            defaults={
                "otp_code": otp,
                "created_at": timezone.now(),
            },
        )

        email_sent = send_otp_email(email, otp)
        if not email_sent:
            DeleteAccountOTP.objects.filter(email=email.lower()).delete()
            return Response(
                {"error": "Failed to send OTP. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        return Response({"message": "OTP sent to your email for account deletion verification."}, status=status.HTTP_200_OK)


class DeleteAccountVerifyView(APIView):
    """
    Verify OTP and delete customer account
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            otp_entry = DeleteAccountOTP.objects.get(email=email.lower())
        except DeleteAccountOTP.DoesNotExist:
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if OTP is expired
        if otp_entry.is_expired():
            otp_entry.delete()
            return Response({"error": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        # Verify OTP
        if otp_entry.otp_code != otp:
            return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(email=email.lower(), role=UserRole.CUSTOMER)
            
            # Delete the user
            user_email = user.email
            user.delete()
            
            # Delete OTP entry
            otp_entry.delete()
            
            # Notify admins
            create_admin_notification(
                user=None, 
                title="Customer account deleted", 
                message=f"Customer account with email: {user_email} has been deleted.",
                event_type="account_deletion"
            )

            return Response({"message": "Your account has been successfully deleted."}, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error deleting account: {str(e)}")
            return Response({"error": "Failed to delete account. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
    