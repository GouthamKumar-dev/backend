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
from users.models import OTP
from django.utils import timezone 

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
            send_otp_email(email, otp)
            # send_otp_sms(phone_number, otp)

            return Response({"message": "OTP sent to email. Please verify to complete signup."}, 
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class LoginRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            password = serializer.validated_data["password"]
            user = authenticate(phone_number=phone_number, password=password)
            if user:
                otp = generate_otp()
                store_otp(user.phone_number, otp)
                store_otp(user.email, otp)

                send_otp_email(user.email, otp)
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

class ResendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data.get("identifier")
        
        if not identifier:
            return Response({"error": "Identifier (email or phone) is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate new OTP
        otp = generate_otp()
        store_otp(identifier, otp)
        
        # Send OTP via Email & SMS
        if "@" in identifier:
            send_otp_email(identifier, otp)
        else:
            # send_otp_sms(identifier, otp)
            pass
        
        return Response({"message": "New OTP sent."}, status=status.HTTP_200_OK)


class ForgotPasswordRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get("phone_number")
        user = CustomUser.objects.filter(phone_number=phone_number).first()

        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure only Admins and Staff can request password reset
        if user.role not in [UserRole.ADMIN, UserRole.STAFF]:
            return Response({"error": "Your user role cannot perform this action."}, status=status.HTTP_403_FORBIDDEN)

        otp = generate_otp()
        store_otp(user.email, otp)
        store_otp(user.phone_number, otp)
        send_otp_email(user.email, otp)
        # send_otp_sms(user.phone_number, otp)

        return Response({"message": "OTP sent to reset password."}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            otp = serializer.validated_data["otp"]
            new_password = serializer.validated_data["new_password"]

            if not verify_otp(phone_number, otp):
                return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.filter(phone_number=phone_number).first()

            if not user:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            # Ensure only Admins and Staff can reset passwords
            if user.role not in [UserRole.ADMIN, UserRole.STAFF]:
                return Response({"error": "Your user role cannot perform this action."}, status=status.HTTP_403_FORBIDDEN)

            user.set_password(new_password)
            user.save()

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

        return Response({"message": "Shipping address updated successfully", "user": UserSerializer(user).data}, status=status.HTTP_200_OK)

# customer login using email and otp
class CustomerLoginRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginWithEmailSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            user = CustomUser.objects.filter(email=email, role=UserRole.CUSTOMER).first()
            if user:
                otp = generate_otp()
                store_otp(user.email, otp)
                send_otp_email(user.email, otp)
                return Response({"message": "OTP sent to email."}, status=status.HTTP_200_OK)
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    