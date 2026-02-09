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
from .quickekyc_service import QuickEKYCService

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
            
            # Testing bypass for test accounts - create if doesn't exist
            if email in ["test@willgibbins.com", "test@example.com"]:
                user = CustomUser.objects.filter(email=email).first()
                if not user:
                    # Create test user automatically
                    user = CustomUser.objects.create(
                        email=email,
                        username="TestUser" if email == "test@willgibbins.com" else "playstoretester",
                        phone_number="1111111111" if email == "test@willgibbins.com" else "0000000000",
                        role=UserRole.ADMIN if email == "test@willgibbins.com" else UserRole.CUSTOMER,
                    )
                    user.set_password("test123")
                    user.save()
                
                # Store hardcoded OTP for testing
                store_otp(email, "000000")
                return Response({"message": "OTP sent to email"}, status=status.HTTP_200_OK)
            
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
            # Email/Identifier → test@example.com OR test@willgibbins.com
            # OTP              → 000000
            # ------------------------------------------------------------------
            if (identifier == "test@example.com" or identifier == "test@willgibbins.com") and otp == "000000":
                user = CustomUser.objects.filter(email=identifier).first()

                # If test user does NOT exist, create it automatically
                if not user:
                    user = CustomUser.objects.create(
                        email=identifier,
                        username="TestUser" if identifier == "test@willgibbins.com" else "playstoretester",
                        phone_number="0000000000" if identifier == "test@example.com" else "1111111111",
                        role=UserRole.ADMIN if identifier == "test@willgibbins.com" else UserRole.CUSTOMER,
                    )
                    user.set_password("test123")  # Set a default password
                    user.save()

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


# ========== VENDOR & KYC MANAGEMENT APIs ==========
from .models import VendorAccount, KYCVerification
from .serializers import (
    VendorAccountSerializer, VendorAccountCreateSerializer,
    KYCVerificationSerializer, KYCVerificationCreateSerializer
)
from .razorpay_service import RazorpayRouteService


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_vendor(request):
    """
    Register a new vendor account
    POST /api/vendors/register/
    
    Request Body:
    {
        "user": <user_id>,
        "business_name": "ABC Electronics",
        "business_type": "Retailer",
        "bank_account_number": "1234567890",
        "bank_ifsc_code": "SBIN0001234",
        "bank_account_holder_name": "ABC Electronics",
        "bank_name": "State Bank of India"
    }
    """
    # Check if user already has a vendor account
    if hasattr(request.user, 'vendor_account'):
        return Response(
            {"error": "User already has a vendor account"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Set user from request
    data = request.data.copy()
    data['user'] = request.user.user_id
    
    serializer = VendorAccountCreateSerializer(data=data)
    if serializer.is_valid():
        vendor = serializer.save()
        
        # Create Razorpay linked account
        try:
            razorpay_service = RazorpayRouteService()
            razorpay_service.create_linked_account(vendor)
            logger.info(f"Created Razorpay linked account for vendor {vendor.vendor_id}")
        except Exception as e:
            # Log error but don't fail registration
            logger.error(f"Failed to create Razorpay account for vendor {vendor.vendor_id}: {str(e)}")
            # Still return success as vendor account is created
        
        # Notify admins
        create_admin_notification(
            user=request.user,
            title="New Vendor Registration",
            message=f"New vendor '{vendor.business_name}' registered by {request.user.username}",
            event_type="vendor_registration"
        )
        
        return Response(
            VendorAccountSerializer(vendor).data,
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_vendor_details(request, vendor_id=None):
    """
    Get vendor account details
    GET /api/vendors/<vendor_id>/ - Get specific vendor (admin/staff or own)
    GET /api/vendors/me/ - Get own vendor account
    """
    try:
        if vendor_id:
            vendor = VendorAccount.objects.get(vendor_id=vendor_id)
            # Check permissions
            if vendor.user != request.user and request.user.role not in [UserRole.ADMIN, UserRole.STAFF]:
                return Response(
                    {"error": "Permission denied"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            # Get own vendor account
            vendor = VendorAccount.objects.get(user=request.user)
        
        serializer = VendorAccountSerializer(vendor)
        return Response(serializer.data)
        
    except VendorAccount.DoesNotExist:
        return Response(
            {"error": "Vendor account not found"},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_kyc_document(request, vendor_id):
    """
    Upload KYC document for vendor
    POST /api/vendors/{vendor_id}/kyc/upload/
    
    Form Data:
    - document_type: 'aadhaar' | 'pan' | 'bank_statement' | 'business_proof' | 'gst_certificate'
    - document_number: String
    - document_file: File
    """
    try:
        vendor = VendorAccount.objects.get(vendor_id=vendor_id)
    except VendorAccount.DoesNotExist:
        return Response(
            {"error": "Vendor not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user owns this vendor account
    if vendor.user != request.user and request.user.role not in [UserRole.ADMIN, UserRole.STAFF]:
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    data = request.data.copy()
    data['vendor'] = vendor_id
    
    serializer = KYCVerificationCreateSerializer(data=data, context={'vendor': vendor})
    if serializer.is_valid():
        kyc_doc = serializer.save()
        
        # Notify admins about new KYC submission
        create_admin_notification(
            user=vendor.user,
            title="KYC Document Submitted",
            message=f"Vendor '{vendor.business_name}' submitted {kyc_doc.document_type} for verification",
            event_type="kyc_submitted"
        )
        
        return Response(
            KYCVerificationSerializer(kyc_doc).data,
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_kyc_status(request, vendor_id):
    """
    Get KYC verification status for vendor
    GET /api/vendors/{vendor_id}/kyc/status/
    """
    try:
        vendor = VendorAccount.objects.get(vendor_id=vendor_id)
    except VendorAccount.DoesNotExist:
        return Response(
            {"error": "Vendor not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if vendor.user != request.user and request.user.role not in [UserRole.ADMIN, UserRole.STAFF]:
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    kyc_documents = vendor.kyc_documents.all()
    
    # Determine overall status
    if not kyc_documents.exists():
        overall_status = "not_submitted"
    elif all(doc.status == 'verified' for doc in kyc_documents):
        overall_status = "verified"
    elif any(doc.status == 'rejected' for doc in kyc_documents):
        overall_status = "rejected"
    elif any(doc.status == 'in_review' for doc in kyc_documents):
        overall_status = "in_review"
    else:
        overall_status = "pending"
    
    return Response({
        "vendor_id": vendor.vendor_id,
        "business_name": vendor.business_name,
        "overall_status": overall_status,
        "kyc_verified": vendor.kyc_verified,
        "account_status": vendor.account_status,
        "documents": KYCVerificationSerializer(kyc_documents, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsAdminOrStaff])
def approve_kyc_document(request, kyc_id):
    """
    Approve or reject KYC document (Admin/Staff only)
    POST /api/kyc/{kyc_id}/review/
    
    Request Body:
    {
        "status": "verified" | "rejected",
        "rejection_reason": "..." (required if rejected)
    }
    """
    try:
        kyc_doc = KYCVerification.objects.get(kyc_id=kyc_id)
    except KYCVerification.DoesNotExist:
        return Response(
            {"error": "KYC document not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    new_status = request.data.get('status')
    if new_status not in ['verified', 'rejected', 'in_review']:
        return Response(
            {"error": "Invalid status. Must be 'verified', 'rejected', or 'in_review'"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    kyc_doc.status = new_status
    kyc_doc.reviewed_by = request.user
    kyc_doc.reviewed_at = timezone.now()
    
    if new_status == 'rejected':
        rejection_reason = request.data.get('rejection_reason', '')
        if not rejection_reason:
            return Response(
                {"error": "rejection_reason is required when rejecting"},
                status=status.HTTP_400_BAD_REQUEST
            )
        kyc_doc.rejection_reason = rejection_reason
    
    kyc_doc.save()
    
    # Check if all vendor documents are verified
    vendor = kyc_doc.vendor
    all_kyc_docs = vendor.kyc_documents.all()
    
    if all(doc.status == 'verified' for doc in all_kyc_docs) and all_kyc_docs.count() >= 2:
        # At least 2 documents must be verified (e.g., Aadhaar + PAN)
        vendor.kyc_verified = True
        vendor.account_status = 'active'
        vendor.verified_at = timezone.now()
        vendor.save()
        
        # Update Razorpay account with KYC data if available
        # This is a placeholder - implement based on actual KYC data
        # try:
        #     razorpay_service = RazorpayRouteService()
        #     kyc_data = {"pan": "...", "gst": "..."}  # Extract from verified docs
        #     razorpay_service.update_linked_account(vendor, kyc_data)
        # except Exception as e:
        #     logger.error(f"Failed to update Razorpay account: {str(e)}")
        
        # Notify vendor
        create_admin_notification(
            user=vendor.user,
            title="KYC Verified - Account Activated",
            message=f"All KYC documents verified. Vendor account '{vendor.business_name}' is now active!",
            event_type="kyc_verified"
        )
    elif new_status == 'rejected':
        # Notify vendor about rejection
        create_admin_notification(
            user=vendor.user,
            title="KYC Document Rejected",
            message=f"Your {kyc_doc.document_type} was rejected: {kyc_doc.rejection_reason}",
            event_type="kyc_rejected"
        )
    
    return Response(KYCVerificationSerializer(kyc_doc).data)


@api_view(['GET'])
@permission_classes([IsAdminOrStaff])
def list_all_vendors(request):
    """
    List all vendors (Admin/Staff only)
    GET /api/vendors/all/
    Supports filtering: ?status=active&kyc_verified=true
    """
    vendors = VendorAccount.objects.all().select_related('user')
    
    # Filters
    account_status = request.GET.get('status')
    if account_status:
        vendors = vendors.filter(account_status=account_status)
    
    kyc_verified = request.GET.get('kyc_verified')
    if kyc_verified:
        kyc_verified_bool = kyc_verified.lower() == 'true'
        vendors = vendors.filter(kyc_verified=kyc_verified_bool)
    
    # Pagination
    paginator = UserPagination()
    paginated_vendors = paginator.paginate_queryset(vendors, request)
    
    serializer = VendorAccountSerializer(paginated_vendors, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminOrStaff])
def list_pending_kyc(request):
    """
    List all pending KYC documents for review (Admin/Staff only)
    GET /api/kyc/pending/
    """
    pending_kyc = KYCVerification.objects.filter(
        status__in=['pending', 'in_review']
    ).select_related('vendor', 'vendor__user').order_by('-submitted_at')
    
    paginator = UserPagination()
    paginated_kyc = paginator.paginate_queryset(pending_kyc, request)
    
    serializer = KYCVerificationSerializer(paginated_kyc, many=True)
    return paginator.get_paginated_response(serializer.data)


# =============================================================================
# PHASE 3: QuickEKYC Automated Verification
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_auto_kyc_verification(request, kyc_id):
    """
    Initiate automated KYC verification via QuickEKYC API.
    POST /api/kyc/<kyc_id>/auto-verify/
    
    Body: {} (empty - uses existing KYC document data)
    
    Returns:
    {
        "success": true,
        "message": "KYC verification initiated",
        "kyc_id": 1,
        "status": "in_review",
        "quickekyc_verification_id": "qekyc_xxx"
    }
    """
    try:
        kyc_doc = KYCVerification.objects.get(kyc_id=kyc_id)
    except KYCVerification.DoesNotExist:
        return Response(
            {"error": "KYC document not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check ownership
    if kyc_doc.vendor.user != request.user and not (request.user.is_staff or request.user.is_superuser):
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check if already verified or in process
    if kyc_doc.status == 'verified':
        return Response(
            {"error": "KYC document already verified"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if kyc_doc.quickekyc_verification_id and kyc_doc.status == 'in_review':
        return Response(
            {"error": "Verification already in progress"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Initiate QuickEKYC verification
    quickekyc_service = QuickEKYCService()
    
    try:
        success = quickekyc_service.process_kyc_document(kyc_doc)
        
        if success:
            # Refresh from database
            kyc_doc.refresh_from_db()
            
            return Response({
                "success": True,
                "message": "KYC verification initiated successfully",
                "kyc_id": kyc_doc.kyc_id,
                "status": kyc_doc.status,
                "quickekyc_verification_id": kyc_doc.quickekyc_verification_id,
                "document_type": kyc_doc.document_type
            })
        else:
            return Response({
                "success": False,
                "message": "Failed to initiate KYC verification",
                "error": kyc_doc.rejection_reason or "Unknown error"
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error initiating auto KYC verification: {str(e)}")
        return Response(
            {"error": f"Verification error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_kyc_verification_status(request, kyc_id):
    """
    Check status of ongoing QuickEKYC verification.
    GET /api/kyc/<kyc_id>/verification-status/
    
    Returns:
    {
        "kyc_id": 1,
        "status": "verified",
        "document_type": "aadhaar",
        "quickekyc_verification_id": "qekyc_xxx",
        "verification_data": {...},
        "submitted_at": "2026-01-24T10:00:00Z",
        "reviewed_at": "2026-01-24T10:05:00Z"
    }
    """
    try:
        kyc_doc = KYCVerification.objects.get(kyc_id=kyc_id)
    except KYCVerification.DoesNotExist:
        return Response(
            {"error": "KYC document not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check ownership
    if kyc_doc.vendor.user != request.user and not (request.user.is_staff or request.user.is_superuser):
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # If has QuickEKYC verification ID, fetch latest status
    if kyc_doc.quickekyc_verification_id:
        quickekyc_service = QuickEKYCService()
        success, response_data = quickekyc_service.get_verification_status(
            kyc_doc.quickekyc_verification_id
        )
        
        if success:
            # Update local status if changed
            new_status = response_data.get('status')
            if new_status == 'verified' and kyc_doc.status != 'verified':
                kyc_doc.status = 'verified'
                kyc_doc.verification_data = response_data
                kyc_doc.reviewed_at = timezone.now()
                kyc_doc.save()
                
                # Check if vendor KYC is complete
                quickekyc_service._check_vendor_kyc_complete(kyc_doc.vendor)
                
            elif new_status == 'failed' and kyc_doc.status != 'rejected':
                kyc_doc.status = 'rejected'
                kyc_doc.rejection_reason = response_data.get('error', 'Verification failed')
                kyc_doc.save()
    
    serializer = KYCVerificationSerializer(kyc_doc)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auto_verify_all_vendor_kyc(request, vendor_id):
    """
    Initiate automated verification for all pending KYC documents of a vendor.
    POST /api/vendors/<vendor_id>/kyc/auto-verify-all/
    
    Body: {} (empty)
    
    Returns:
    {
        "success": true,
        "message": "Auto-verification initiated for 3 documents",
        "results": [
            {
                "kyc_id": 1,
                "document_type": "aadhaar",
                "success": true,
                "status": "in_review"
            },
            ...
        ]
    }
    """
    try:
        vendor = VendorAccount.objects.get(vendor_id=vendor_id)
    except VendorAccount.DoesNotExist:
        return Response(
            {"error": "Vendor not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check ownership
    if vendor.user != request.user and not (request.user.is_staff or request.user.is_superuser):
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get all pending KYC documents
    pending_docs = KYCVerification.objects.filter(
        vendor=vendor,
        status__in=['pending', 'resubmit']
    )
    
    if not pending_docs.exists():
        return Response({
            "success": False,
            "message": "No pending KYC documents found"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    quickekyc_service = QuickEKYCService()
    results = []
    
    for kyc_doc in pending_docs:
        try:
            success = quickekyc_service.process_kyc_document(kyc_doc)
            kyc_doc.refresh_from_db()
            
            results.append({
                "kyc_id": kyc_doc.kyc_id,
                "document_type": kyc_doc.document_type,
                "success": success,
                "status": kyc_doc.status,
                "quickekyc_verification_id": kyc_doc.quickekyc_verification_id
            })
        except Exception as e:
            logger.error(f"Error auto-verifying KYC {kyc_doc.kyc_id}: {str(e)}")
            results.append({
                "kyc_id": kyc_doc.kyc_id,
                "document_type": kyc_doc.document_type,
                "success": False,
                "error": str(e)
            })
    
    successful_count = sum(1 for r in results if r.get('success', False))
    
    return Response({
        "success": True,
        "message": f"Auto-verification initiated for {successful_count}/{len(results)} documents",
        "results": results
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def quickekyc_webhook(request):
    """
    Webhook endpoint for QuickEKYC verification callbacks.
    POST /api/kyc/webhook/quickekyc/
    
    Body: (from QuickEKYC)
    {
        "event": "verification.completed",
        "verification_id": "qekyc_xxx",
        "status": "verified",
        "document_type": "aadhaar",
        "data": {...},
        "timestamp": "2026-01-24T10:00:00Z",
        "signature": "..."
    }
    """
    # Verify webhook signature (for security)
    from django.conf import settings
    import hmac
    import hashlib
    
    webhook_secret = getattr(settings, 'QUICKEKYC_WEBHOOK_SECRET', '')
    if webhook_secret:
        signature = request.headers.get('X-QuickEKYC-Signature', '')
        payload = request.body.decode('utf-8')
        
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Invalid QuickEKYC webhook signature")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED
            )
    
    # Process webhook
    webhook_data = request.data
    quickekyc_service = QuickEKYCService()
    
    try:
        success = quickekyc_service.handle_webhook(webhook_data)
        
        if success:
            return Response({"status": "success"})
        else:
            return Response(
                {"status": "failed", "error": "Failed to process webhook"},
                status=status.HTTP_400_BAD_REQUEST
            )
    except Exception as e:
        logger.error(f"Error processing QuickEKYC webhook: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ========================================
# NEW: OWNER DASHBOARD VIEWS
# ========================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_dashboard(request):
    """
    Owner dashboard with platform overview:
    - Total admins, customers, orders, revenue
    - Platform commission (2%) breakdown
    - Recent activity summary
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can access this dashboard"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from orders.models import Order, PaymentSettlement
        from products.models import Product
        from django.db.models import Count, Sum, Q
        from datetime import datetime, timedelta
        
        # Count statistics
        total_admins = CustomUser.objects.filter(role='admin').count()
        total_customers = CustomUser.objects.filter(role='customer').count()
        total_products = Product.objects.count()
        
        # Order statistics
        total_orders = Order.objects.count()
        completed_orders = Order.objects.filter(status='delivered').count()
        pending_orders = Order.objects.filter(
            status__in=['pending', 'confirmed', 'shipped', 'out_for_delivery']
        ).count()
        
        # Revenue statistics
        total_revenue = Order.objects.filter(
            status='delivered'
        ).aggregate(total=Sum('total_price'))['total'] or 0
        
        platform_commission = Order.objects.filter(
            status='delivered'
        ).aggregate(total=Sum('commission_amount'))['total'] or 0
        
        admin_settlement_total = Order.objects.filter(
            status='delivered'
        ).aggregate(total=Sum('admin_settlement_amount'))['total'] or 0
        
        # Recent activity (last 7 days)
        week_ago = datetime.now() - timedelta(days=7)
        recent_orders = Order.objects.filter(created_at__gte=week_ago).count()
        recent_admins = CustomUser.objects.filter(
            role='admin', 
            created_at__gte=week_ago
        ).count()
        
        # Top performing admins
        top_admins = CustomUser.objects.filter(role='admin').annotate(
            order_count=Count('admin_orders', filter=Q(admin_orders__status='delivered')),
            total_revenue=Sum('admin_orders__total_price', filter=Q(admin_orders__status='delivered'))
        ).order_by('-total_revenue')[:5]
        
        top_admins_data = [{
            'id': admin.id,
            'username': admin.username,
            'email': admin.email,
            'order_count': admin.order_count or 0,
            'total_revenue': float(admin.total_revenue or 0)
        } for admin in top_admins]
        
        return Response({
            'statistics': {
                'total_admins': total_admins,
                'total_customers': total_customers,
                'total_products': total_products,
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'pending_orders': pending_orders,
            },
            'revenue': {
                'total_revenue': float(total_revenue),
                'platform_commission': float(platform_commission),
                'admin_settlement_total': float(admin_settlement_total),
                'commission_percentage': 2.0
            },
            'recent_activity': {
                'orders_last_7_days': recent_orders,
                'new_admins_last_7_days': recent_admins
            },
            'top_admins': top_admins_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching owner dashboard: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_payment_history(request):
    """
    Platform owner's payment/commission history
    Shows all completed settlements with platform commission details
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can access payment history"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from orders.models import PaymentSettlement
        from django.db.models import Q
        
        # Get all settlements
        settlements = PaymentSettlement.objects.select_related(
            'order', 'admin'
        ).order_by('-settlement_date')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            settlements = settlements.filter(status=status_filter)
        
        # Filter by date range if provided
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            settlements = settlements.filter(settlement_date__gte=start_date)
        if end_date:
            settlements = settlements.filter(settlement_date__lte=end_date)
        
        # Pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 20
        result_page = paginator.paginate_queryset(settlements, request)
        
        settlements_data = [{
            'id': s.id,
            'order_id': s.order.id,
            'admin': {
                'id': s.admin.id,
                'username': s.admin.username,
                'email': s.admin.email
            },
            'order_total': float(s.order.total_price),
            'platform_commission': float(s.order.commission_amount),
            'admin_settlement': float(s.amount),
            'status': s.status,
            'settlement_date': s.settlement_date,
            'transaction_id': s.transaction_id or 'N/A'
        } for s in result_page]
        
        return paginator.get_paginated_response(settlements_data)
        
    except Exception as e:
        logger.error(f"Error fetching payment history: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_audit_log(request):
    """
    Platform audit log showing all system activities
    - Admin registrations
    - Product additions
    - Order completions
    - Settlement transactions
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can access audit logs"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from orders.models import Order
        from products.models import Product
        from datetime import datetime, timedelta
        
        # Get date range (default: last 30 days)
        days = int(request.query_params.get('days', 30))
        start_date = datetime.now() - timedelta(days=days)
        
        # Aggregate activities
        activities = []
        
        # New admin registrations
        new_admins = CustomUser.objects.filter(
            role='admin',
            date_joined__gte=start_date
        ).order_by('-date_joined')
        
        for admin in new_admins:
            activities.append({
                'type': 'admin_registration',
                'timestamp': admin.date_joined,
                'description': f"New admin registered: {admin.username}",
                'details': {
                    'admin_id': admin.id,
                    'email': admin.email
                }
            })
        
        # New products
        new_products = Product.objects.filter(
            created_at__gte=start_date
        ).select_related('admin').order_by('-created_at')
        
        for product in new_products:
            activities.append({
                'type': 'product_created',
                'timestamp': product.created_at,
                'description': f"New product added: {product.name}",
                'details': {
                    'product_id': product.id,
                    'admin': product.admin.username if product.admin else 'N/A',
                    'price': float(product.price)
                }
            })
        
        # Completed orders
        completed_orders = Order.objects.filter(
            status='delivered',
            updated_at__gte=start_date
        ).select_related('admin', 'user').order_by('-updated_at')
        
        for order in completed_orders:
            activities.append({
                'type': 'order_completed',
                'timestamp': order.updated_at,
                'description': f"Order #{order.id} delivered",
                'details': {
                    'order_id': order.id,
                    'admin': order.admin.username if order.admin else 'N/A',
                    'customer': order.user.username,
                    'amount': float(order.final_price),
                    'commission': float(order.platform_commission)
                }
            })
        
        # Sort all activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 50
        
        # Manual pagination for list
        page = int(request.query_params.get('page', 1))
        start_idx = (page - 1) * paginator.page_size
        end_idx = start_idx + paginator.page_size
        page_activities = activities[start_idx:end_idx]
        
        return Response({
            'count': len(activities),
            'next': f"?page={page + 1}" if end_idx < len(activities) else None,
            'previous': f"?page={page - 1}" if page > 1 else None,
            'results': page_activities
        })
        
    except Exception as e:
        logger.error(f"Error fetching audit log: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_list_admins(request):
    """
    List all admins with their performance metrics
    - Total products
    - Total orders
    - Total revenue
    - Commission paid to platform
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can access admin list"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.db.models import Count, Sum, Q
        
        # Get all admins with aggregated stats
        admins = CustomUser.objects.filter(role='admin').annotate(
            product_count=Count('admin_products'),
            total_orders=Count('admin_orders'),
            completed_orders=Count('admin_orders', filter=Q(admin_orders__status='delivered')),
            total_revenue=Sum('admin_orders__total_price', filter=Q(admin_orders__status='delivered')),
            platform_commission_total=Sum('admin_orders__commission_amount', filter=Q(admin_orders__status='delivered'))
        ).order_by('-total_revenue')
        
        # Search filter
        search = request.query_params.get('search')
        if search:
            admins = admins.filter(
                Q(username__icontains=search) | 
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        admins_data = [{
            'id': admin.id,
            'username': admin.username,
            'email': admin.email,
            'phone_number': admin.phone_number,
            'date_joined': admin.created_at,
            'is_active': admin.is_active,
            'statistics': {
                'product_count': admin.product_count or 0,
                'total_orders': admin.total_orders or 0,
                'completed_orders': admin.completed_orders or 0,
                'total_revenue': float(admin.total_revenue or 0),
                'platform_commission_paid': float(admin.platform_commission_total or 0),
                'admin_earnings': float((admin.total_revenue or 0) - (admin.platform_commission_total or 0))
            }
        } for admin in admins]
        
        return Response({
            'count': len(admins_data),
            'results': admins_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching admin list: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== BANK DETAILS MANAGEMENT ====================

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def manage_bank_details(request):
    """
    Admin can view and update their bank details
    GET: Retrieve current bank details
    PUT: Update bank details
    """
    try:
        user = request.user
        
        # Only admins can manage bank details
        if user.role != 'admin':
            return Response(
                {"error": "Only admins can manage bank details"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.method == 'GET':
            from .serializers import BankDetailsSerializer
            serializer = BankDetailsSerializer(user)
            return Response(serializer.data)
        
        elif request.method == 'PUT':
            from .serializers import BankDetailsSerializer
            
            # Admin can update their details, but verification status cannot be changed
            serializer = BankDetailsSerializer(user, data=request.data, partial=True)
            
            if serializer.is_valid():
                # If bank details are being updated, reset verification
                if any(field in request.data for field in ['bank_account_number', 'bank_ifsc_code']):
                    user.bank_details_verified = False
                    user.bank_verified_at = None
                    user.bank_verified_by = None
                
                serializer.save()
                
                return Response({
                    "message": "Bank details updated successfully",
                    "data": serializer.data
                })
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error managing bank details: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def owner_list_admins_bank_details(request):
    """
    Owner can view all admins with their bank details for verification
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can access admin bank details"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.db.models import Q
        from .serializers import AdminProfileSerializer
        
        # Get all admins
        admins = CustomUser.objects.filter(role='admin').order_by('-created_at')
        
        # Filter options
        verification_status = request.query_params.get('verification_status')  # verified, unverified, pending
        search = request.query_params.get('search')
        
        if verification_status == 'verified':
            admins = admins.filter(bank_details_verified=True)
        elif verification_status == 'unverified':
            admins = admins.filter(bank_details_verified=False)
        elif verification_status == 'pending':
            # Has bank details but not verified
            admins = admins.filter(
                bank_details_verified=False
            ).exclude(bank_account_number__isnull=True).exclude(bank_account_number='')
        
        if search:
            admins = admins.filter(
                Q(username__icontains=search) | 
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        serializer = AdminProfileSerializer(admins, many=True)
        
        # Mask account numbers for security (show last 4 digits)
        for admin_data in serializer.data:
            if admin_data.get('bank_account_number'):
                account_num = admin_data['bank_account_number']
                if len(account_num) > 4:
                    admin_data['bank_account_number_masked'] = '*' * (len(account_num) - 4) + account_num[-4:]
                else:
                    admin_data['bank_account_number_masked'] = account_num
        
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error fetching admin bank details: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def owner_verify_bank_details(request, admin_id):
    """
    Owner verifies admin's bank details
    POST: Verify or reject bank details
    """
    try:
        # Verify owner role
        if request.user.role != 'owner':
            return Response(
                {"error": "Only platform owner can verify bank details"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get admin user
        try:
            admin = CustomUser.objects.get(user_id=admin_id, role='admin')
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Admin not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if bank details exist
        if not admin.bank_account_number or not admin.bank_ifsc_code:
            return Response(
                {"error": "Admin has not provided bank details yet"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        action = request.data.get('action')  # 'approve' or 'reject'
        remarks = request.data.get('remarks', '')
        
        if action == 'approve':
            admin.bank_details_verified = True
            admin.bank_verified_by = request.user
            admin.bank_verified_at = timezone.now()
            admin.save()
            
            return Response({
                "message": f"Bank details for {admin.username} verified successfully",
                "admin_id": admin.user_id,
                "verified_at": admin.bank_verified_at
            })
        
        elif action == 'reject':
            admin.bank_details_verified = False
            admin.bank_verified_at = None
            admin.bank_verified_by = None
            admin.save()
            
            # TODO: Send notification to admin about rejection
            
            return Response({
                "message": f"Bank details for {admin.username} rejected",
                "remarks": remarks
            })
        
        else:
            return Response(
                {"error": "Invalid action. Use 'approve' or 'reject'"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Exception as e:
        logger.error(f"Error verifying bank details: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    
    
    
    