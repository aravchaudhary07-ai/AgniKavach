import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Hotspot, Infrastructure, IndustrialBaseline


class SpatialCrossReferencer:
    """
    Spatial Cross-Referencing Engine for AgniKavach.
    Uses GeoPandas and Shapely to cross-reference satellite thermal anomalies
    against Indian Land Use / Land Cover (LULC) boundaries, industrial baseline buffers,
    and emergency response infrastructure (fire stations & hospitals).
    """

    def __init__(self):
        self.data_dir = Path(__file__).resolve().parent.parent / "data"
        self.lulc_path = self.data_dir / "india_landcover_zones.geojson"
        
        if not self.lulc_path.exists():
            raise FileNotFoundError(f"LULC GeoJSON not found at: {self.lulc_path}")

        print(f"[LOAD] Loading Indian LULC boundary polygons from {self.lulc_path.name}...")
        self.lulc_gdf = gpd.read_file(self.lulc_path)
        if self.lulc_gdf.crs is None or self.lulc_gdf.crs.to_epsg() != 4326:
            self.lulc_gdf = self.lulc_gdf.set_crs(epsg=4326, allow_override=True)
        print(f"[SUCCESS] Loaded {len(self.lulc_gdf)} regional LULC zones into GeoPandas.")

    def cross_reference_point(
        self,
        lat: float,
        lon: float,
        db: Session
    ) -> Dict[str, Any]:
        """
        Perform spatial point-in-polygon and proximity checks for a single coordinate.
        """
        pt = Point(lon, lat)
        
        # 1. Point-in-Polygon against Land Use / Land Cover zones
        matched_zone = None
        for _, row in self.lulc_gdf.iterrows():
            if row.geometry.contains(pt):
                matched_zone = row
                break

        if matched_zone is not None:
            zone_type = matched_zone["zone_type"]
            zone_name = matched_zone["name"]
            vulnerability = float(matched_zone.get("vulnerability_weight", 0.5))
            fuel_density = matched_zone.get("fuel_density", "medium")
            canopy_pct = float(matched_zone.get("canopy_cover_pct", 10.0))
        else:
            zone_type = "scrub_or_grassland"
            zone_name = "Unclassified Rural Terrain"
            vulnerability = 0.5
            fuel_density = "medium"
            canopy_pct = 15.0

        # 2. Check if coordinate falls inside an Industrial Baseline buffer
        pt_wkt = f"POINT({lon} {lat})"
        in_industrial_baseline = False
        baseline_name = None
        typical_frp_limit = 0.0

        # Query industrial baselines where ST_Contains(geom, point) is True
        intersecting_baseline = (
            db.query(IndustrialBaseline)
            .filter(func.ST_Contains(IndustrialBaseline.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)))
            .first()
        )

        if intersecting_baseline:
            in_industrial_baseline = True
            baseline_name = intersecting_baseline.name
            typical_frp_limit = intersecting_baseline.typical_frp_threshold
            zone_type = "industrial" # Force override if inside verified industrial flare buffer

        # 3. Proximity to nearest Fire Station
        nearest_fire_station = (
            db.query(
                Infrastructure.name,
                (func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)) / 1000.0).label("dist_km"),
                Infrastructure.contact_phone,
                Infrastructure.capacity
            )
            .filter(Infrastructure.type == "fire_station")
            .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)))
            .first()
        )

        # 4. Proximity to nearest Medical / Hospital facility
        nearest_hospital = (
            db.query(
                Infrastructure.name,
                (func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)) / 1000.0).label("dist_km"),
                Infrastructure.contact_phone,
                Infrastructure.capacity
            )
            .filter(Infrastructure.type == "hospital")
            .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)))
            .first()
        )

        return {
            "latitude": lat,
            "longitude": lon,
            "land_cover_type": zone_type,
            "zone_name": zone_name,
            "vulnerability_factor": vulnerability,
            "fuel_density": fuel_density,
            "canopy_cover_pct": canopy_pct,
            "in_industrial_baseline": in_industrial_baseline,
            "industrial_facility": baseline_name,
            "industrial_frp_threshold": typical_frp_limit,
            "nearest_fire_station": nearest_fire_station[0] if nearest_fire_station else None,
            "dist_fire_station_km": round(float(nearest_fire_station[1]), 2) if nearest_fire_station else None,
            "fire_station_phone": nearest_fire_station[2] if nearest_fire_station else None,
            "nearest_hospital": nearest_hospital[0] if nearest_hospital else None,
            "dist_hospital_km": round(float(nearest_hospital[1]), 2) if nearest_hospital else None,
            "hospital_phone": nearest_hospital[2] if nearest_hospital else None
        }

    def enrich_active_hotspots(self, db: Optional[Session] = None) -> pd.DataFrame:
        """
        Fetch all hotspots currently in PostgreSQL and enrich them with
        spatial LULC context, industrial baseline flags, and emergency proximity.
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            hotspots = db.query(Hotspot).all()
            print(f"[SPATIAL] Cross-referencing {len(hotspots)} database hotspots...")
            records = []

            for h in hotspots:
                spatial_ctx = self.cross_reference_point(h.latitude, h.longitude, db)
                combined = {
                    "hotspot_id": h.id,
                    "acq_date": h.acq_date,
                    "acq_time": h.acq_time,
                    "satellite": h.satellite,
                    "instrument": h.instrument,
                    "confidence": h.confidence,
                    "bright_ti4": h.bright_ti4,
                    "bright_ti5": h.bright_ti5,
                    "frp": h.frp,
                    "daynight": h.daynight,
                    **spatial_ctx
                }
                records.append(combined)

            df = pd.DataFrame(records)
            print(f"[SUCCESS] Spatial enrichment complete. Generated {len(df)} feature rows.")
            return df
        finally:
            if close_session:
                db.close()


if __name__ == "__main__":
    engine = SpatialCrossReferencer()
    enriched_df = engine.enrich_active_hotspots()
    
    print("\n--- Enriched Spatial Features Preview ---")
    cols_to_show = [
        "hotspot_id", "land_cover_type", "frp", "in_industrial_baseline", 
        "nearest_fire_station", "dist_fire_station_km", "nearest_hospital", "dist_hospital_km"
    ]
    print(enriched_df[cols_to_show].to_string(index=False))
