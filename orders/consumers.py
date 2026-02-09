"""
WebSocket Consumer for Real-Time Order Tracking
Handles live location updates for delivery partners and customers.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from orders.models import Order, DeliveryPartner, OrderLocationHistory
from decimal import Decimal

User = get_user_model()
logger = logging.getLogger(__name__)


class OrderTrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time order tracking.
    
    Usage:
    - Connect: ws://domain/ws/tracking/order/<order_id>/
    - Receives: Real-time location updates from delivery partner
    - Sends: Location updates to all connected clients (customer, admin)
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'order_tracking_{self.order_id}'
        
        # Verify order exists and user has permission
        try:
            has_permission = await self.check_permission()
            if not has_permission:
                await self.close()
                return
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # Send current order status and last known location
            await self.send_current_status()
            
            logger.info(f"WebSocket connected: order_id={self.order_id}")
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected: order_id={self.order_id}, code={close_code}")
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket.
        
        Expected message formats:
        
        1. Location Update (from delivery partner):
        {
            "type": "location_update",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy": 10.5,
            "speed": 20.0,
            "heading": 90.0
        }
        
        2. Status Update (from delivery partner):
        {
            "type": "status_update",
            "status": "Shipped|Out for Delivery|Delivered",
            "message": "Package picked up from warehouse"
        }
        
        3. Request Current Status (from customer):
        {
            "type": "get_status"
        }
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'location_update':
                await self.handle_location_update(data)
                
            elif message_type == 'status_update':
                await self.handle_status_update(data)
                
            elif message_type == 'get_status':
                await self.send_current_status()
                
            else:
                await self.send(text_data=json.dumps({
                    'error': f'Unknown message type: {message_type}'
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await self.send(text_data=json.dumps({
                'error': 'Failed to process message'
            }))
    
    async def handle_location_update(self, data):
        """Handle location update from delivery partner."""
        user = self.scope.get('user')
        
        # Verify user is delivery partner for this order
        is_delivery_partner = await self.is_delivery_partner_for_order(user)
        if not is_delivery_partner:
            await self.send(text_data=json.dumps({
                'error': 'Only delivery partner can send location updates'
            }))
            return
        
        # Extract location data
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy', 0)
        speed = data.get('speed', 0)
        heading = data.get('heading', 0)
        
        if not latitude or not longitude:
            await self.send(text_data=json.dumps({
                'error': 'Latitude and longitude required'
            }))
            return
        
        # Save to database
        location_saved = await self.save_location_update(
            latitude, longitude, accuracy, speed, heading
        )
        
        if location_saved:
            # Broadcast to all clients in this room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'location_message',
                    'latitude': latitude,
                    'longitude': longitude,
                    'accuracy': accuracy,
                    'speed': speed,
                    'heading': heading,
                    'timestamp': location_saved['timestamp']
                }
            )
    
    async def handle_status_update(self, data):
        """Handle order status update from delivery partner."""
        user = self.scope.get('user')
        
        # Verify user is delivery partner for this order
        is_delivery_partner = await self.is_delivery_partner_for_order(user)
        if not is_delivery_partner:
            await self.send(text_data=json.dumps({
                'error': 'Only delivery partner can update status'
            }))
            return
        
        status = data.get('status')
        message = data.get('message', '')
        
        if not status:
            await self.send(text_data=json.dumps({
                'error': 'Status required'
            }))
            return
        
        # Update order status
        status_updated = await self.update_order_status(status)
        
        if status_updated:
            # Broadcast to all clients
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'status_message',
                    'status': status,
                    'message': message,
                    'timestamp': status_updated['timestamp']
                }
            )
    
    async def send_current_status(self):
        """Send current order status and last location to client."""
        order_data = await self.get_order_data()
        
        if order_data:
            await self.send(text_data=json.dumps({
                'type': 'current_status',
                'order': order_data
            }))
    
    # Message handlers (receive from channel layer)
    
    async def location_message(self, event):
        """Send location update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'location_update',
            'latitude': event['latitude'],
            'longitude': event['longitude'],
            'accuracy': event['accuracy'],
            'speed': event['speed'],
            'heading': event['heading'],
            'timestamp': event['timestamp']
        }))
    
    async def status_message(self, event):
        """Send status update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': event['status'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))
    
    async def eta_message(self, event):
        """Send ETA update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'eta_update',
            'estimated_arrival': event['estimated_arrival'],
            'distance_remaining': event['distance_remaining']
        }))
    
    # Database operations (async wrappers)
    
    @database_sync_to_async
    def check_permission(self):
        """Check if user has permission to track this order."""
        user = self.scope.get('user')
        
        if not user or not user.is_authenticated:
            return False
        
        try:
            order = Order.objects.get(order_id=self.order_id)
            
            # Allow: order owner, delivery partner, or admin
            if order.user == user:
                return True
            
            if user.is_staff or user.is_superuser:
                return True
            
            # Check if user is delivery partner for this order
            if hasattr(order, 'delivery_partner') and order.delivery_partner:
                if order.delivery_partner.user == user:
                    return True
            
            return False
            
        except Order.DoesNotExist:
            return False
    
    @database_sync_to_async
    def is_delivery_partner_for_order(self, user):
        """Check if user is the delivery partner assigned to this order."""
        try:
            order = Order.objects.get(order_id=self.order_id)
            if hasattr(order, 'delivery_partner') and order.delivery_partner:
                return order.delivery_partner.user == user
            return False
        except Order.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_location_update(self, latitude, longitude, accuracy, speed, heading):
        """Save location update to database."""
        try:
            order = Order.objects.get(order_id=self.order_id)
            
            if not hasattr(order, 'delivery_partner') or not order.delivery_partner:
                return None
            
            location = OrderLocationHistory.objects.create(
                order=order,
                delivery_partner=order.delivery_partner,
                latitude=Decimal(str(latitude)),
                longitude=Decimal(str(longitude)),
                accuracy=Decimal(str(accuracy)),
                speed=Decimal(str(speed)) if speed else None,
                heading=Decimal(str(heading)) if heading else None
            )
            
            return {
                'location_id': location.location_id,
                'timestamp': location.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to save location: {str(e)}")
            return None
    
    @database_sync_to_async
    def update_order_status(self, status):
        """Update order status in database."""
        try:
            order = Order.objects.get(order_id=self.order_id)
            
            # Validate status
            valid_statuses = ['Processing', 'Shipped', 'Out for Delivery', 'Delivered']
            if status not in valid_statuses:
                return None
            
            order.status = status
            order.save()
            
            return {
                'order_id': order.order_id,
                'status': order.status,
                'timestamp': order.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to update status: {str(e)}")
            return None
    
    @database_sync_to_async
    def get_order_data(self):
        """Get current order data with latest location."""
        try:
            order = Order.objects.select_related(
                'user', 'delivery_partner', 'delivery_partner__user'
            ).get(order_id=self.order_id)
            
            # Get last location
            last_location = None
            if hasattr(order, 'location_history') and order.location_history.exists():
                location = order.location_history.latest('timestamp')
                last_location = {
                    'latitude': float(location.latitude),
                    'longitude': float(location.longitude),
                    'accuracy': float(location.accuracy),
                    'speed': float(location.speed) if location.speed else None,
                    'heading': float(location.heading) if location.heading else None,
                    'timestamp': location.timestamp.isoformat()
                }
            
            # Build response
            order_data = {
                'order_id': order.order_id,
                'status': order.status,
                'shipping_address': order.shipping_address,
                'total_price': str(order.total_price),
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat(),
                'last_location': last_location
            }
            
            # Add delivery partner info if available
            if hasattr(order, 'delivery_partner') and order.delivery_partner:
                dp = order.delivery_partner
                order_data['delivery_partner'] = {
                    'name': dp.name,
                    'phone_number': dp.phone_number,
                    'vehicle_type': dp.vehicle_type,
                    'vehicle_number': dp.vehicle_number
                }
            
            return order_data
            
        except Exception as e:
            logger.error(f"Failed to get order data: {str(e)}")
            return None


class DeliveryPartnerTrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for delivery partner's own tracking dashboard.
    Shows all assigned orders and allows batch location updates.
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        user = self.scope.get('user')
        
        if not user or not user.is_authenticated:
            await self.close()
            return
        
        # Check if user is a delivery partner
        is_dp = await self.is_delivery_partner(user)
        if not is_dp:
            await self.close()
            return
        
        self.room_group_name = f'delivery_partner_{user.user_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send current assigned orders
        await self.send_assigned_orders()
        
        logger.info(f"Delivery partner WebSocket connected: user_id={user.user_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle messages from delivery partner."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_orders':
                await self.send_assigned_orders()
                
            elif message_type == 'update_location':
                # Update location for all active orders
                await self.update_all_orders_location(data)
                
        except Exception as e:
            logger.error(f"Error in delivery partner WebSocket: {str(e)}")
    
    async def send_assigned_orders(self):
        """Send list of assigned orders to delivery partner."""
        orders = await self.get_assigned_orders()
        
        await self.send(text_data=json.dumps({
            'type': 'assigned_orders',
            'orders': orders
        }))
    
    async def update_all_orders_location(self, data):
        """Update location for all active delivery orders."""
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if not latitude or not longitude:
            return
        
        # This will update location for all active orders
        # and broadcast to respective order tracking rooms
        await self.broadcast_location_to_orders(latitude, longitude, data)
    
    @database_sync_to_async
    def is_delivery_partner(self, user):
        """Check if user is a delivery partner."""
        try:
            DeliveryPartner.objects.get(user=user)
            return True
        except DeliveryPartner.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_assigned_orders(self):
        """Get all orders assigned to this delivery partner."""
        user = self.scope.get('user')
        
        try:
            dp = DeliveryPartner.objects.get(user=user)
            orders = Order.objects.filter(
                delivery_partner=dp,
                status__in=['Shipped', 'Out for Delivery']
            ).values(
                'order_id', 'status', 'shipping_address', 
                'total_price', 'created_at'
            )
            
            return list(orders)
            
        except Exception as e:
            logger.error(f"Failed to get assigned orders: {str(e)}")
            return []
    
    async def broadcast_location_to_orders(self, latitude, longitude, data):
        """Broadcast location update to all assigned order rooms."""
        orders = await self.get_active_order_ids()
        
        for order_id in orders:
            room_name = f'order_tracking_{order_id}'
            await self.channel_layer.group_send(
                room_name,
                {
                    'type': 'location_message',
                    'latitude': latitude,
                    'longitude': longitude,
                    'accuracy': data.get('accuracy', 0),
                    'speed': data.get('speed', 0),
                    'heading': data.get('heading', 0),
                    'timestamp': data.get('timestamp', '')
                }
            )
    
    @database_sync_to_async
    def get_active_order_ids(self):
        """Get IDs of all active orders for this delivery partner."""
        user = self.scope.get('user')
        
        try:
            dp = DeliveryPartner.objects.get(user=user)
            order_ids = Order.objects.filter(
                delivery_partner=dp,
                status__in=['Shipped', 'Out for Delivery']
            ).values_list('order_id', flat=True)
            
            return list(order_ids)
            
        except Exception as e:
            logger.error(f"Failed to get active orders: {str(e)}")
            return []
