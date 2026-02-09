"""
Delivery Tracking Service
Handles GPS tracking, ETA calculation, and geofencing for orders.
"""

import logging
from typing import Dict, Optional, Tuple, List
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from orders.models import Order, DeliveryPartner, OrderLocationHistory
import math

logger = logging.getLogger(__name__)


class DeliveryTrackingService:
    """
    Service for managing delivery tracking and location-based features.
    """
    
    # Constants
    EARTH_RADIUS_KM = 6371  # Earth's radius in kilometers
    AVERAGE_SPEED_KMH = 30  # Average delivery speed in km/h
    
    def __init__(self):
        """Initialize delivery tracking service."""
        pass
    
    def calculate_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula.
        
        Args:
            lat1: Latitude of point 1
            lon1: Longitude of point 1
            lat2: Latitude of point 2
            lon2: Longitude of point 2
            
        Returns:
            Distance in kilometers
        """
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
        c = 2 * math.asin(math.sqrt(a))
        
        distance = self.EARTH_RADIUS_KM * c
        return round(distance, 2)
    
    def calculate_eta(self, current_lat: float, current_lon: float,
                     dest_lat: float, dest_lon: float,
                     current_speed: Optional[float] = None) -> Dict:
        """
        Calculate estimated time of arrival.
        
        Args:
            current_lat: Current latitude
            current_lon: Current longitude
            dest_lat: Destination latitude
            dest_lon: Destination longitude
            current_speed: Current speed in km/h (optional)
            
        Returns:
            Dict with distance, duration, and ETA
        """
        # Calculate distance
        distance_km = self.calculate_distance(
            current_lat, current_lon, dest_lat, dest_lon
        )
        
        # Use current speed or average speed
        speed = current_speed if current_speed and current_speed > 0 else self.AVERAGE_SPEED_KMH
        
        # Calculate duration in minutes
        duration_hours = distance_km / speed
        duration_minutes = int(duration_hours * 60)
        
        # Calculate ETA
        eta = timezone.now() + timedelta(minutes=duration_minutes)
        
        return {
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'eta': eta.isoformat(),
            'speed_kmh': speed
        }
    
    def is_within_geofence(self, lat: float, lon: float,
                          center_lat: float, center_lon: float,
                          radius_km: float = 0.5) -> bool:
        """
        Check if location is within geofence radius.
        
        Args:
            lat: Current latitude
            lon: Current longitude
            center_lat: Geofence center latitude
            center_lon: Geofence center longitude
            radius_km: Radius in kilometers (default 0.5km = 500m)
            
        Returns:
            True if within geofence, False otherwise
        """
        distance = self.calculate_distance(lat, lon, center_lat, center_lon)
        return distance <= radius_km
    
    def record_location_update(self, order_id: int, latitude: float,
                              longitude: float, status: Optional[str] = None,
                              notes: Optional[str] = None) -> Optional[OrderLocationHistory]:
        """
        Record a location update for an order.
        
        Args:
            order_id: Order ID
            latitude: GPS latitude
            longitude: GPS longitude
            status: Status at this location (optional)
            notes: Additional notes (optional)
            
        Returns:
            OrderLocationHistory instance or None if failed
        """
        try:
            order = Order.objects.select_related('delivery_partner').get(order_id=order_id)
            
            # Create location even if no delivery partner (for testing)
            location = OrderLocationHistory.objects.create(
                order=order,
                delivery_partner=order.delivery_partner if hasattr(order, 'delivery_partner') and order.delivery_partner else None,
                latitude=Decimal(str(latitude)),
                longitude=Decimal(str(longitude)),
                status_at_location=status,
                notes=notes
            )
            
            logger.info(f"Location recorded for order {order_id}: ({latitude}, {longitude})")
            return location
            
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to record location: {str(e)}")
            return None
    
    def get_location_history(self, order_id: int, limit: int = 50) -> List[Dict]:
        """
        Get location history for an order.
        
        Args:
            order_id: Order ID
            limit: Maximum number of records (default 50)
            
        Returns:
            List of location records
        """
        try:
            locations = OrderLocationHistory.objects.filter(
                order_id=order_id
            ).order_by('-recorded_at')[:limit]
            
            return [
                {
                    'history_id': loc.history_id,
                    'latitude': float(loc.latitude),
                    'longitude': float(loc.longitude),
                    'status_at_location': loc.status_at_location,
                    'recorded_at': loc.recorded_at.isoformat()
                }
                for loc in locations
            ]
            
        except Exception as e:
            logger.error(f"Failed to get location history: {str(e)}")
            return []
    
    def get_current_location(self, order_id: int) -> Optional[Dict]:
        """
        Get most recent location for an order.
        
        Args:
            order_id: Order ID
            
        Returns:
            Location dict or None
        """
        try:
            location = OrderLocationHistory.objects.filter(
                order_id=order_id
            ).latest('recorded_at')
            
            return {
                'history_id': location.history_id,
                'latitude': float(location.latitude),
                'longitude': float(location.longitude),
                'status_at_location': location.status_at_location,
                'recorded_at': location.recorded_at.isoformat(),
                'delivery_partner': {
                    'name': location.delivery_partner.name,
                    'phone_number': location.delivery_partner.phone_number
                } if location.delivery_partner else None
            }
            
        except OrderLocationHistory.DoesNotExist:
            logger.info(f"No location history for order {order_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get current location: {str(e)}")
            return None
    
    def calculate_order_eta(self, order_id: int, 
                           dest_lat: float, dest_lon: float,
                           avg_speed_kmh: float = 30.0) -> Optional[Dict]:
        """
        Calculate ETA for an order based on current location.
        
        Args:
            order_id: Order ID
            dest_lat: Destination latitude
            dest_lon: Destination longitude
            avg_speed_kmh: Average delivery speed in km/h (default 30)
            
        Returns:
            ETA dict or None if no location available
        """
        current_location = self.get_current_location(order_id)
        
        if not current_location:
            return None
        
        eta_data = self.calculate_eta(
            current_location['latitude'],
            current_location['longitude'],
            dest_lat,
            dest_lon,
            avg_speed_kmh  # Use provided average speed
        )
        
        return eta_data
    
    def check_delivery_arrival(self, order_id: int,
                              dest_lat: float, dest_lon: float,
                              radius_km: float = 0.1) -> Tuple[bool, Optional[float]]:
        """
        Check if delivery partner has arrived at destination.
        
        Args:
            order_id: Order ID
            dest_lat: Destination latitude
            dest_lon: Destination longitude
            radius_km: Arrival radius in km (default 100m)
            
        Returns:
            Tuple of (is_arrived, distance_km)
        """
        current_location = self.get_current_location(order_id)
        
        if not current_location:
            return False, None
        
        distance = self.calculate_distance(
            current_location['latitude'],
            current_location['longitude'],
            dest_lat,
            dest_lon
        )
        
        is_arrived = distance <= radius_km
        
        if is_arrived:
            logger.info(f"Delivery partner arrived at destination for order {order_id}")
        
        return is_arrived, distance
    
    def get_nearby_delivery_partners(self, lat: float, lon: float,
                                     radius_km: float = 5.0,
                                     only_available: bool = True) -> List[Dict]:
        """
        Find delivery partners near a location.
        
        Args:
            lat: Search center latitude
            lon: Search center longitude
            radius_km: Search radius in kilometers
            only_available: Only return available partners
            
        Returns:
            List of nearby delivery partners
        """
        try:
            # Get all delivery partners
            query = DeliveryPartner.objects.all()
            
            if only_available:
                query = query.filter(is_available=True)
            
            nearby_partners = []
            
            for partner in query:
                # Get last known location
                last_location = OrderLocationHistory.objects.filter(
                    delivery_partner=partner
                ).order_by('-recorded_at').first()
                
                if last_location:
                    distance = self.calculate_distance(
                        lat, lon,
                        float(last_location.latitude),
                        float(last_location.longitude)
                    )
                    
                    if distance <= radius_km:
                        nearby_partners.append({
                            'partner_id': partner.partner_id,
                            'name': partner.name,
                            'phone_number': partner.phone_number,
                            'vehicle_type': partner.vehicle_type,
                            'distance_km': distance,
                            'last_seen': last_location.recorded_at.isoformat()
                        })
            
            # Sort by distance
            nearby_partners.sort(key=lambda x: x['distance_km'])
            
            return nearby_partners
            
        except Exception as e:
            logger.error(f"Failed to find nearby partners: {str(e)}")
            return []
    
    def auto_assign_delivery_partner(self, order_id: int,
                                     pickup_lat: float,
                                     pickup_lon: float) -> Optional[DeliveryPartner]:
        """
        Automatically assign nearest available delivery partner to order.
        
        Args:
            order_id: Order ID
            pickup_lat: Pickup location latitude
            pickup_lon: Pickup location longitude
            
        Returns:
            Assigned DeliveryPartner or None
        """
        try:
            order = Order.objects.get(order_id=order_id)
            
            if order.delivery_partner:
                logger.info(f"Order {order_id} already has delivery partner assigned")
                return order.delivery_partner
            
            # Find nearby available partners
            nearby_partners = self.get_nearby_delivery_partners(
                pickup_lat, pickup_lon,
                radius_km=10.0,
                only_available=True
            )
            
            if not nearby_partners:
                logger.warning(f"No available delivery partners found near order {order_id}")
                return None
            
            # Assign nearest partner
            nearest_partner_id = nearby_partners[0]['partner_id']
            partner = DeliveryPartner.objects.get(partner_id=nearest_partner_id)
            
            order.delivery_partner = partner
            order.status = 'Shipped'
            order.save()
            
            # Mark partner as unavailable
            partner.is_available = False
            partner.save()
            
            logger.info(f"Auto-assigned partner {partner.name} to order {order_id}")
            
            return partner
            
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to auto-assign partner: {str(e)}")
            return None
    
    def get_delivery_route(self, order_id: int,
                          max_points: int = 100) -> List[Tuple[float, float]]:
        """
        Get delivery route as list of coordinates.
        
        Args:
            order_id: Order ID
            max_points: Maximum number of points to return
            
        Returns:
            List of (latitude, longitude) tuples
        """
        try:
            locations = OrderLocationHistory.objects.filter(
                order_id=order_id
            ).order_by('recorded_at')[:max_points]
            
            route = [
                (float(loc.latitude), float(loc.longitude))
                for loc in locations
            ]
            
            return route
            
        except Exception as e:
            logger.error(f"Failed to get delivery route: {str(e)}")
            return []
    
    def calculate_route_statistics(self, order_id: int) -> Dict:
        """
        Calculate statistics for delivery route.
        
        Args:
            order_id: Order ID
            
        Returns:
            Dict with route statistics
        """
        try:
            locations = OrderLocationHistory.objects.filter(
                order_id=order_id
            ).order_by('recorded_at')
            
            if not locations.exists():
                return {
                    'total_points': 0,
                    'total_distance_km': 0,
                    'duration_minutes': 0,
                    'average_speed_kmh': 0
                }
            
            # Calculate total distance
            total_distance = 0
            prev_loc = None
            
            for loc in locations:
                if prev_loc:
                    distance = self.calculate_distance(
                        float(prev_loc.latitude), float(prev_loc.longitude),
                        float(loc.latitude), float(loc.longitude)
                    )
                    total_distance += distance
                prev_loc = loc
            
            # Calculate duration
            first_loc = locations.first()
            last_loc = locations.last()
            duration = (last_loc.recorded_at - first_loc.recorded_at).total_seconds() / 60
            
            # Calculate average speed
            avg_speed = (total_distance / duration * 60) if duration > 0 else 0
            
            return {
                'total_points': locations.count(),
                'total_distance_km': round(total_distance, 2),
                'duration_minutes': int(duration),
                'average_speed_kmh': round(avg_speed, 2),
                'start_time': first_loc.recorded_at.isoformat(),
                'end_time': last_loc.recorded_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate route stats: {str(e)}")
            return {}
