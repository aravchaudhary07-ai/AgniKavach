import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from geoalchemy2.elements import WKTElement
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Infrastructure, IndustrialBaseline


class OSMLoader:
    """
    OpenStreetMap (OSM) and Spatial Infrastructure Loader.
    Ingests emergency response assets (fire stations, hospitals) and known industrial
    heat baselines into PostGIS for spatial cross-referencing and emergency routing.
    """

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self):
        self.data_dir = Path(__file__).resolve().parent.parent / "data"

    def query_overpass_fire_stations(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        timeout: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Query the live OpenStreetMap Overpass API for fire stations within a bounding box.
        Bbox order: south, west, north, east
        """
        query = f"""
        [out:json][timeout:{timeout}];
        (
          node["amenity"="fire_station"]({south},{west},{north},{east});
          way["amenity"="fire_station"]({south},{west},{north},{east});
        );
        out center;
        """
        print(f"[OSM] Querying Overpass API for fire stations in bbox [{south}, {west}, {north}, {east}]...")
        response = requests.post(self.OVERPASS_URL, data={"data": query}, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        elements = data.get("elements", [])
        stations = []
        for el in elements:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:en") or f"Fire Station ({el['id']})"
            phone = tags.get("phone") or tags.get("contact:phone") or "101"
            
            if lat and lon:
                stations.append({
                    "name": name,
                    "type": "fire_station",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "capacity": 3,
                    "contact_phone": phone,
                    "address": tags.get("addr:full") or tags.get("addr:street") or "OpenStreetMap Node"
                })

        print(f"[SUCCESS] Found {len(stations)} fire stations from OpenStreetMap.")
        return stations

    def load_curated_infrastructure(self) -> List[Dict[str, Any]]:
        """Load curated Indian emergency response infrastructure."""
        infra_path = self.data_dir / "sample_infrastructure_india.json"
        if not infra_path.exists():
            raise FileNotFoundError(f"Infrastructure data file not found at {infra_path}")

        print(f"[LOAD] Reading curated infrastructure from {infra_path.name}...")
        with open(infra_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[SUCCESS] Loaded {len(data)} emergency infrastructure assets.")
        return data

    def load_industrial_baselines(self) -> List[Dict[str, Any]]:
        """Load known industrial heat baselines (refineries, power plants, steel mills)."""
        baseline_path = self.data_dir / "sample_industrial_baselines.json"
        if not baseline_path.exists():
            raise FileNotFoundError(f"Baselines data file not found at {baseline_path}")

        print(f"[LOAD] Reading industrial heat baselines from {baseline_path.name}...")
        with open(baseline_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[SUCCESS] Loaded {len(data)} industrial baseline facilities.")
        return data

    def ingest_infrastructure(
        self,
        infra_list: List[Dict[str, Any]],
        db: Optional[Session] = None
    ) -> Dict[str, int]:
        """Insert infrastructure assets into PostGIS table `infrastructure`."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        new_count = 0
        skipped_count = 0

        try:
            for item in infra_list:
                name = item["name"]
                lat = float(item["latitude"])
                lon = float(item["longitude"])

                # Check duplicate by name and coordinates
                exists = db.query(Infrastructure).filter(
                    Infrastructure.name == name,
                    Infrastructure.latitude == lat,
                    Infrastructure.longitude == lon
                ).first()

                if exists:
                    skipped_count += 1
                    continue

                geom_wkt = f"POINT({lon} {lat})"
                station = Infrastructure(
                    name=name,
                    type=item.get("type", "fire_station"),
                    latitude=lat,
                    longitude=lon,
                    geom=WKTElement(geom_wkt, srid=4326),
                    capacity=item.get("capacity", 2),
                    contact_phone=item.get("contact_phone"),
                    address=item.get("address")
                )
                db.add(station)
                new_count += 1

            db.commit()
            print(f"[DB] Infrastructure complete: {new_count} inserted, {skipped_count} skipped.")
            return {"inserted": new_count, "skipped": skipped_count}
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_session:
                db.close()

    def ingest_industrial_baselines(
        self,
        baseline_list: List[Dict[str, Any]],
        db: Optional[Session] = None
    ) -> Dict[str, int]:
        """Insert industrial heat zones into `industrial_baselines` with PostGIS polygons."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        new_count = 0
        skipped_count = 0

        try:
            for item in baseline_list:
                name = item["name"]
                cat = item.get("category", "industrial")
                lat = float(item["latitude"])
                lon = float(item["longitude"])
                buffer_m = float(item.get("buffer_radius_m", 1500.0))

                exists = db.query(IndustrialBaseline).filter(
                    IndustrialBaseline.name == name
                ).first()

                if exists:
                    skipped_count += 1
                    continue

                # Generate a buffered polygon around the industrial point in PostGIS
                # Using 1 degree ~ 111,000 meters for approximate WGS84 polygon buffer
                deg_buffer = buffer_m / 111320.0
                min_lon, max_lon = lon - deg_buffer, lon + deg_buffer
                min_lat, max_lat = lat - deg_buffer, lat + deg_buffer
                poly_wkt = (
                    f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
                    f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
                )

                baseline = IndustrialBaseline(
                    name=name,
                    category=cat,
                    latitude=lat,
                    longitude=lon,
                    buffer_radius_m=buffer_m,
                    geom=WKTElement(poly_wkt, srid=4326),
                    typical_frp_threshold=float(item.get("typical_frp_threshold", 50.0)),
                    notes=item.get("notes")
                )
                db.add(baseline)
                new_count += 1

            db.commit()
            print(f"[DB] Industrial baselines complete: {new_count} inserted, {skipped_count} skipped.")
            return {"inserted": new_count, "skipped": skipped_count}
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_session:
                db.close()

    def run(self) -> Dict[str, Any]:
        """Execute full infrastructure & baseline ingestion."""
        infra_data = self.load_curated_infrastructure()
        infra_stats = self.ingest_infrastructure(infra_data)

        baseline_data = self.load_industrial_baselines()
        baseline_stats = self.ingest_industrial_baselines(baseline_data)

        return {
            "infrastructure": infra_stats,
            "industrial_baselines": baseline_stats
        }


if __name__ == "__main__":
    loader = OSMLoader()
    results = loader.run()
    print("\n--- Ingestion Results ---")
    print(json.dumps(results, indent=2))
