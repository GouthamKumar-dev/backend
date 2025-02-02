from rest_framework import serializers
from .models import Product, Category, Favorite

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    favorite_count = serializers.SerializerMethodField()  # Use SerializerMethodField

    class Meta:
        model = Product
        fields = [
            "product_id",
            "name",
            "description",
            "price",
            "stock",
            "category",
            "created_at",
            "updated_at",
            "is_active",
            "favorite_count",  # Include favorite count
        ]

    def get_favorite_count(self, obj):
        return obj.favorite_count()

    def create(self, validated_data):
        category_data = validated_data.pop('category')
        category, _ = Category.objects.get_or_create(**category_data)
        product = Product.objects.create(category=category, **validated_data)
        return product

    def update(self, instance, validated_data):
        if 'category' in validated_data:
            category_data = validated_data.pop('category')
            category, _ = Category.objects.get_or_create(**category_data)
            instance.category = category

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)  # Nested product details
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Favorite
        fields = ['favorite_id', 'user', 'product', 'product_id','is_active']
        read_only_fields = ['favorite_id', 'user']
