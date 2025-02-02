from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, LoginView, CustomTokenObtainPairView, LogoutView, CustomTokenRefreshView, user_me
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
)


# router = DefaultRouter()
# router.register(r'users', UserViewSet)

urlpatterns = [
    # my profile only
    path('me/', user_me, name='user-me'),
    # Add token creation, login, and logout endpoints
    # Token related
    path('login/', LoginView.as_view(), name='login'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),  # Get access and refresh tokens
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),  # Refresh access token
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # Verify access token
    path('logout/', LogoutView.as_view(), name='logout'),
]

