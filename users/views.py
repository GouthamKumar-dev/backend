# views.py
from rest_framework import viewsets
from .models import CustomUser
from .serializers import UserSerializer,CustomTokenObtainPairSerializer,CustomTokenRefreshSerializer
from .permissions import IsAdminUser, IsStaffUser, IsOwnerOrAdmin
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView

from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response

from django.contrib.auth import authenticate
from rest_framework import status
from ecommerce.logger import logger

class CustomRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token['user_id'] = user.user_id  # Add custom user_id claim
        return token

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')
        email = request.data.get('email')
        username = request.data.get('username')
        # Try to find the user by phone number
        user = CustomUser.objects.filter(phone_number=phone_number).first()

        # If user does not exist, create a new user
        if not user:
            if not username:
                username = phone_number
            user = CustomUser.objects.create_user(
                phone_number=phone_number,
                password=password,
                username=username,
                email=email  # Or any other logic for generating username
            )
            return Response({
                'message': 'User created successfully, and here is your token!',
                'refresh': str(RefreshToken.for_user(user)),
                'access': str(RefreshToken.for_user(user).access_token),
            }, status=status.HTTP_201_CREATED)

        # If user exists, authenticate them
        user = authenticate(phone_number=phone_number, password=password, email = email)

        if user:
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': 'Login successful',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_200_OK)

        return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

# user view
class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ['list', 'create']:
            return [IsAdminUser()]
        return [IsOwnerOrAdmin()]

class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer

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
                print("I am here")
                token.blacklist()
                return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
            else:
                return Response(custom_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Log the error for debugging
            logger.error(f"Error during logout: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

