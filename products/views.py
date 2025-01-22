# views.py
from rest_framework import viewsets
from .models import Product, Category
from .serializers import (ProductSerializer,CategorySerializer)
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
