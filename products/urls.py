from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, FavoriteViewSet, UploadedImageViewSet

router = DefaultRouter()
router.register(r'productdetail', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'favorites', FavoriteViewSet, basename='favorites')  # Add favorites endpoint
router.register(r'uploads', UploadedImageViewSet, basename='uploads') 

urlpatterns = router.urls

# Serve media files during development

