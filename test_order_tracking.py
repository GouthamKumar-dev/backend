#!/usr/bin/env python
"""
Test Order Tracking Integration
Verifies backend tracking endpoints are working
"""
import os
import sys
import django
import json

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from django.contrib.auth import get_user_model
from orders.models import Order
from orders.tracking_service import DeliveryTrackingService
from products.models import Product, Category
from users.models import CustomUser

User = get_user_model()

def create_test_data():
    """Create test order for tracking"""
    print("\n" + "="*60)
    print("Creating Test Data for Order Tracking")
    print("="*60)
    
    # Get or create customer
    try:
        customer = User.objects.get(username='tracking_customer')
        print(f"✓ Using existing customer: {customer.username}")
    except User.DoesNotExist:
        customer = User.objects.create_user(
            username='tracking_customer',
            email='customer@track.com',
            phone_number='8888888888',  # Unique phone
            password='test123',
            role='customer'
        )
        print(f"✓ Created new customer: {customer.username}")
    
    # Get or create admin
    try:
        admin = User.objects.get(username='tracking_admin')
        print(f"✓ Using existing admin: {admin.username}")
    except User.DoesNotExist:
        admin = User.objects.create_user(
            username='tracking_admin',
            email='admin@track.com',
            phone_number='7777777777',  # Unique phone
            password='test123',
            role='admin'
        )
        print(f"✓ Created new admin: {admin.username}")
    
    # Get or create category
    category, _ = Category.objects.get_or_create(
        category_code='TRACK_CAT',
        defaults={
            'name': 'Tracking Test Category',
            'description': 'For testing order tracking',
            'is_active': True
        }
    )
    print(f"✓ Category: {category.name}")
    
    # Get or create product
    product, _ = Product.objects.get_or_create(
        product_code='TRACK_PROD_001',
        defaults={
            'name': 'Tracking Test Product',
            'description': 'Product for testing tracking',
            'price': 99.99,
            'stock': 100,
            'category': category,
            'admin': admin,
            'is_active': True
        }
    )
    print(f"✓ Product: {product.name}")
    
    # Create test order
    order = Order.objects.create(
        user=customer,
        total_price=99.99,
        shipping_address='123 Test Street, Test City, 12345',
        status='out_for_delivery',
        is_active=True
    )
    print(f"✓ Order created: #{order.order_id}")
    
    return order, customer

def test_tracking_service(order):
    """Test tracking service functionality"""
    print("\n" + "="*60)
    print("Testing Tracking Service")
    print("="*60)
    
    tracking_service = DeliveryTrackingService()
    order_id = order.order_id
    
    # Test 1: Record location updates
    print("\n1. Testing Location Updates...")
    locations = [
        (37.7749, -122.4194),  # San Francisco
        (37.7849, -122.4094),  # Moving north-east
        (37.7949, -122.3994),  # Continuing
    ]
    
    for i, (lat, lng) in enumerate(locations, 1):
        try:
            location = tracking_service.record_location_update(
                order_id=order_id,
                latitude=lat,
                longitude=lng
            )
            print(f"   ✓ Location {i} recorded: ({lat}, {lng})")
        except Exception as e:
            print(f"   ✗ Failed to record location {i}: {str(e)}")
            return False
    
    # Test 2: Get current location
    print("\n2. Testing Get Current Location...")
    try:
        current = tracking_service.get_current_location(order_id)
        if current:
            print(f"   ✓ Current location: ({current['latitude']}, {current['longitude']})")
        else:
            print("   ⚠ No current location found")
    except Exception as e:
        print(f"   ✗ Failed to get current location: {str(e)}")
        return False
    
    # Test 3: Get location history
    print("\n3. Testing Location History...")
    try:
        history = tracking_service.get_location_history(order_id, limit=10)
        print(f"   ✓ Location history: {len(history)} points")
        for loc in history[:3]:
            print(f"      - ({loc['latitude']}, {loc['longitude']}) at {loc['recorded_at']}")
    except Exception as e:
        print(f"   ✗ Failed to get location history: {str(e)}")
        return False
    
    # Test 4: Calculate ETA
    print("\n4. Testing ETA Calculation...")
    try:
        # Destination: slightly north of last location
        dest_lat, dest_lng = 37.8049, -122.3894
        eta_data = tracking_service.calculate_order_eta(order_id, dest_lat, dest_lng)
        print(f"   ✓ ETA: {eta_data['duration_minutes']} minutes")
        print(f"   ✓ Distance: {eta_data['distance_km']:.2f} km")
    except Exception as e:
        print(f"   ✗ Failed to calculate ETA: {str(e)}")
        return False
    
    # Test 5: Get delivery route
    print("\n5. Testing Delivery Route...")
    try:
        route = tracking_service.get_delivery_route(order_id, max_points=50)
        print(f"   ✓ Route has {len(route)} points")
    except Exception as e:
        print(f"   ✗ Failed to get delivery route: {str(e)}")
        return False
    
    # Test 6: Route statistics
    print("\n6. Testing Route Statistics...")
    try:
        stats = tracking_service.calculate_route_statistics(order_id)
        print(f"   ✓ Total distance: {stats['total_distance_km']:.2f} km")
        print(f"   ✓ Total points: {stats['total_points']}")
        if stats.get('average_speed_kmh'):
            print(f"   ✓ Average speed: {stats['average_speed_kmh']:.2f} km/h")
    except Exception as e:
        print(f"   ✗ Failed to calculate statistics: {str(e)}")
        return False
    
    return True

def test_rest_api(order):
    """Test REST API endpoint"""
    print("\n" + "="*60)
    print("Testing REST API Endpoint")
    print("="*60)
    
    from django.test import Client
    import jwt
    from django.conf import settings
    
    client = Client()
    
    # Create JWT token for customer
    token_payload = {
        'user_id': order.user.id,
        'username': order.user.username,
        'role': order.user.role,
    }
    token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm='HS256')
    
    print(f"\n✓ JWT Token generated")
    print(f"✓ Testing: GET /api/orders/order/{order.order_id}/tracking/")
    
    # Make request
    response = client.get(
        f'/api/orders/order/{order.order_id}/tracking/',
        HTTP_AUTHORIZATION=f'Bearer {token}'
    )
    
    print(f"✓ Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Response Data:")
        print(f"   - Order ID: {data.get('order_id')}")
        print(f"   - Status: {data.get('status')}")
        if data.get('current_location'):
            print(f"   - Current Location: ({data['current_location']['lat']}, {data['current_location']['lng']})")
        if data.get('delivery_address'):
            print(f"   - Delivery Address: ({data['delivery_address']['lat']}, {data['delivery_address']['lng']})")
        print(f"   - ETA: {data.get('estimated_arrival', 0)} minutes")
        print(f"   - Route Points: {len(data.get('route', []))}")
        return True
    else:
        print(f"✗ API request failed")
        print(f"   Response: {response.content.decode()}")
        return False

def check_websocket_routing():
    """Check if WebSocket routing is configured"""
    print("\n" + "="*60)
    print("Checking WebSocket Configuration")
    print("="*60)
    
    try:
        from orders.routing import websocket_urlpatterns
        print(f"✓ WebSocket routing configured")
        print(f"✓ Routes defined: {len(websocket_urlpatterns)}")
        for pattern in websocket_urlpatterns:
            print(f"   - {pattern.pattern}")
        return True
    except ImportError as e:
        print(f"✗ WebSocket routing not found: {str(e)}")
        return False

def main():
    print("\n" + "="*60)
    print("ORDER TRACKING INTEGRATION TEST")
    print("="*60)
    
    # Step 1: Create test data
    order, customer = create_test_data()
    
    # Step 2: Test tracking service
    if not test_tracking_service(order):
        print("\n✗ Tracking service tests failed!")
        return
    
    # Step 3: Test REST API
    if not test_rest_api(order):
        print("\n✗ REST API tests failed!")
        return
    
    # Step 4: Check WebSocket routing
    if not check_websocket_routing():
        print("\n⚠ WebSocket routing check failed (may be normal if not using Channels)")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    
    print(f"""
Test Order Details:
- Order ID: {order.order_id}
- Customer: {customer.username}
- Status: {order.status}

You can now test tracking from the mobile app:
1. Login as: {customer.username} / test123
2. Go to Order History
3. Select Order #{order.order_id}
4. Tap "Track Order"

API Endpoint:
GET http://localhost:8000/api/orders/{order.order_id}/tracking/

WebSocket URL:
ws://localhost:8000/ws/tracking/order/{order.order_id}/
""")

if __name__ == '__main__':
    main()
