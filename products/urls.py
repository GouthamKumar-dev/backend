from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, FavoriteViewSet, UploadedImageViewSet, SearchViewSet

router = DefaultRouter()
router.register(r'productdetail', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'favorites', FavoriteViewSet, basename='favorites')
router.register(r'uploads', UploadedImageViewSet, basename='uploads')

urlpatterns = router.urls  # Include router-generated URLs

# Manually add search endpoint
urlpatterns += [
    path('search/', SearchViewSet.as_view(), name='search'),  
]
