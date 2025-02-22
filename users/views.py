# views.py
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from .models import CustomUser
from .serializers import UserSerializer,CustomTokenObtainPairSerializer,CustomTokenRefreshSerializer,SignupSerializer, LoginSerializer, CreateUserSerializer
from .permissions import IsAdminUser, IsStaffUser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView

from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response

from django.contrib.auth import authenticate
from rest_framework import status
from ecommerce.logger import logger
from .serializers import SignupSerializer, LoginSerializer, OTPVerifySerializer, ResetPasswordSerializer
from .utils import generate_otp, store_otp, send_otp_email, send_otp_sms, verify_otp

class CustomRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token['user_id'] = user.user_id  # Add custom user_id claim
        return token

class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            otp = generate_otp()
            store_otp(user.email, otp)
            store_otp(user.phone_number, otp)

            # Send OTP via Email & SMS
            send_otp_email(user.email, otp)
            send_otp_sms(user.phone_number, otp)

            return Response({"message": "OTP sent to email and phone number."}, status=status.HTTP_201_CREATED)
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
                send_otp_sms(user.phone_number, otp)

                return Response({"message": "OTP sent to email and phone number."}, status=status.HTTP_200_OK)
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data["identifier"]
            otp = serializer.validated_data["otp"]

            if verify_otp(identifier, otp):
                user = CustomUser.objects.filter(email=identifier).first() or CustomUser.objects.filter(phone_number=identifier).first()
                if user:
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        "user": {"username": user.username, "email": user.email, "phone_number": user.phone_number, "role":user.role},
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    }, status=status.HTTP_200_OK)
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordRequestOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get("phone_number")
        user = CustomUser.objects.filter(phone_number=phone_number).first()
        if user:
            otp = generate_otp()
            store_otp(user.email, otp)
            store_otp(user.phone_number, otp)
            send_otp_email(user.email, otp)
            send_otp_sms(user.phone_number, otp)
            return Response({"message": "OTP sent to reset password."}, status=status.HTTP_200_OK)
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            otp = serializer.validated_data["otp"]
            new_password = serializer.validated_data["new_password"]

            if verify_otp(phone_number, otp):
                user = CustomUser.objects.filter(phone_number=phone_number).first()
                if user:
                    user.set_password(new_password)
                    user.save()
                    return Response({"message": "Password reset successful."}, status=status.HTTP_200_OK)
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"error": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
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
        'email': request.user.email
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

