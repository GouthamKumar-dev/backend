from django.urls import path
from .views import  CustomTokenObtainPairView, LogoutView, CustomTokenRefreshView, user_me, SignupView, LoginView, CreateUserView
from rest_framework_simplejwt.views import TokenVerifyView

urlpatterns = [
    # my profile only
    path('me/', user_me, name='user-me'),
    # Add token creation, signup, login, and logout endpoints
    # Token related
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('create-user/', CreateUserView.as_view(), name='create-user'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),  # Get access and refresh tokens
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),  # Refresh access token
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # Verify access token
    path('logout/', LogoutView.as_view(), name='logout')
]

