from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, FavoriteViewSet

router = DefaultRouter()
router.register(r'productdetail', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'favorites', FavoriteViewSet, basename='favorites')  # Add favorites endpoint

urlpatterns = router.urls
