from rest_framework import serializers
from .models import Product, Category, Favorite, UploadedImage

class CategorySerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()  # New field to include image URLs

    class Meta:
        model = Category
        fields = '__all__'

    def get_images(self, obj):
        """ Fetch all image URLs related to this category or product """
        request = self.context.get("request")
        # Check if the object is Category or Product and fetch associated images accordingly
        images = UploadedImage.objects.filter(category=obj) if isinstance(obj, Category) else UploadedImage.objects.filter(product=obj)

        if request:
            return [request.build_absolute_uri(img.image.url) for img in images if img.image]
        return [img.image.url for img in images if img.image]  # Use relative URL if request is None

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    favorite_count = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()  # New field to include image URLs

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
            "favorite_count",
            "images",  # Add images field
        ]

    def get_favorite_count(self, obj):
        return obj.favorite_count()

    def get_images(self, obj):
        """ Fetch all image URLs related to this product """
        request = self.context.get("request")
        images = UploadedImage.objects.filter(product=obj)  # Get images related to this product

        if request:
            return [request.build_absolute_uri(img.image.url) for img in images if img.image]
        return [img.image.url for img in images if img.image]  # Use relative URL if request is None

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
        fields = ['favorite_id', 'user', 'product', 'product_id', 'is_active']
        read_only_fields = ['favorite_id', 'user']


class UploadedImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = UploadedImage
        fields = ['id','image', 'product', 'category', 'uploaded_at']

    def get_image_url(self, obj):
        """ Generate a URL for the stored image """
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None
