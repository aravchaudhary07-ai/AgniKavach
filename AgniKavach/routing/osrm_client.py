import os
import sys
import math
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Hotspot, Infrastructure


class OSRMClient:
    """
    Open Source Routing Machine (OSRM) Client.
    Calculates turn-by-turn driving paths, distance, and estimated travel time (ETA)
    for emergency fire brigades and medical ambulances.
    """

    OSRM_PUBLIC_API = "https://router.project-osrm.org/route/v1/driving"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def get_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        route_type: str = "emergency_dispatch"
    ) -> Dict[str, Any]:
        """
        Request driving route from start (lat, lon) to end (lat, lon).
        Tries live OSRM public routing service first, with graceful fallback.
        """
        # OSRM coordinate format: lon,lat;lon,lat
        url = (
            f"{self.OSRM_PUBLIC_API}/{start_lon:.6f},{start_lat:.6f};"
            f"{end_lon:.6f},{end_lat:.6f}?overview=full&geometries=geojson&steps=true"
        )

        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    primary_route = data["routes"][0]
                    dist_km = round(primary_route["distance"] / 1000.0, 2)
                    duration_min = round(primary_route["duration"] / 60.0, 1)
                    geojson_geom = primary_route["geometry"]

                    return {
                        "source": "osrm_live",
                        "route_type": route_type,
                        "distance_km": dist_km,
                        "duration_minutes": duration_min,
                        "geometry": geojson_geom,
                        "steps_count": len(primary_route.get("legs", [{}])[0].get("steps", []))
                    }
        except Exception as e:
            # Network error / rate limit / offline fallback
            pass

        # Robust Fallback: Great-Circle with Road Tortuosity Factor (1.28x) & Emergency Speed (50 km/h)
        return self._compute_fallback_route(start_lat, start_lon, end_lat, end_lon, route_type)

    def _compute_fallback_route(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        route_type: str
    ) -> Dict[str, Any]:
        """Haversine distance with road winding multiplier (1.28x) for offline simulations."""
        R = 6371.0 # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        straight_km = R * c

        # Average road driving factor: ~1.28 times straight line distance
        road_distance_km = round(straight_km * 1.28, 2)
        
        # Average emergency vehicle speed: ~50 km/h in rural/forest terrain
        est_minutes = round((road_distance_km / 50.0) * 60.0, 1)

        # Generate interpolated waypoint coordinates for map visualization
        n_points = max(5, int(road_distance_km // 5))
        coords = []
        for i in range(n_points + 1):
            fraction = i / n_points
            lat_i = lat1 + (lat2 - lat1) * fraction
            lon_i = lon1 + (lon2 - lon1) * fraction
            coords.append([round(lon_i, 6), round(lat_i, 6)])

        return {
            "source": "simulated_road_network",
            "route_type": route_type,
            "distance_km": max(0.5, road_distance_km),
            "duration_minutes": max(2.0, est_minutes),
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "steps_count": n_points
        }

    def compute_multi_agency_routes(
        self,
        hotspot_id: int,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Calculate complete multi-agency emergency paths for a fire incident:
          1. Path 1: Closest Fire Station -> Incident (Fire suppression deployment)
          2. Path 2: Incident -> Closest Hospital / Trauma Centre (Ambulance casualty route)
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
            if not hotspot:
                raise ValueError(f"Hotspot #{hotspot_id} not found in database.")

            h_lat = hotspot.latitude
            h_lon = hotspot.longitude

            # 1. Locate Nearest Fire Station
            nearest_fire = (
                db.query(Infrastructure)
                .filter(Infrastructure.type == "fire_station")
                .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h_lon, h_lat), 4326)))
                .first()
            )

            # 2. Locate Nearest Hospital / Medical Facility
            nearest_hospital = (
                db.query(Infrastructure)
                .filter(Infrastructure.type == "hospital")
                .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h_lon, h_lat), 4326)))
                .first()
            )

            results = {
                "hotspot_id": hotspot.id,
                "incident_type": hotspot.fire_type,
                "risk_score": hotspot.risk_score,
                "incident_coordinates": [h_lat, h_lon],
                "fire_brigade_route": None,
                "medical_ambulance_route": None
            }

            if nearest_fire:
                fire_route = self.get_route(
                    start_lat=nearest_fire.latitude,
                    start_lon=nearest_fire.longitude,
                    end_lat=h_lat,
                    end_lon=h_lon,
                    route_type="fire_tender_dispatch"
                )
                results["fire_brigade_route"] = {
                    "station_id": nearest_fire.id,
                    "station_name": nearest_fire.name,
                    "station_coordinates": [nearest_fire.latitude, nearest_fire.longitude],
                    "contact_phone": nearest_fire.contact_phone,
                    **fire_route
                }

            if nearest_hospital:
                med_route = self.get_route(
                    start_lat=h_lat,
                    start_lon=h_lon,
                    end_lat=nearest_hospital.latitude,
                    end_lon=nearest_hospital.longitude,
                    route_type="ambulance_evacuation"
                )
                results["medical_ambulance_route"] = {
                    "hospital_id": nearest_hospital.id,
                    "hospital_name": nearest_hospital.name,
                    "hospital_coordinates": [nearest_hospital.latitude, nearest_hospital.longitude],
                    "contact_phone": nearest_hospital.contact_phone,
                    **med_route
                }

            return results
        finally:
            if close_session:
                db.close()


if __name__ == "__main__":
    client = OSRMClient()
    print("[ROUTING] Computing Multi-Agency Turn-by-Turn Paths for Simlipal Forest Fire (Hotspot #1)...")
    routes = client.compute_multi_agency_routes(hotspot_id=1)

    print("\n=== MULTI-AGENCY EMERGENCY ROUTE RESULTS ===")
    print(f"Incident: Hotspot #{routes['hotspot_id']} ({routes['incident_type'].upper()}, Risk: {routes['risk_score']}/100)")
    
    fb = routes["fire_brigade_route"]
    if fb:
        print(f"\n[FIRE SERVICE ROUTE] Source: {fb['source'].upper()}")
        print(f"  Station: {fb['station_name']} -> Incident")
        print(f"  Road Distance: {fb['distance_km']} km | Estimated Time of Arrival: {fb['duration_minutes']} mins")
        print(f"  Contact Phone: {fb['contact_phone']}")

    med = routes["medical_ambulance_route"]
    if med:
        print(f"\n[MEDICAL AMBULANCE ROUTE] Source: {med['source'].upper()}")
        print(f"  Incident -> Hospital: {med['hospital_name']}")
        print(f"  Road Distance: {med['distance_km']} km | Estimated Time to Care: {med['duration_minutes']} mins")
        print(f"  Contact Phone: {med['contact_phone']}")
