import os
import csv
import json
import io
import sys
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
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Hotspot


class FirmsClient:
    """
    NASA FIRMS (Fire Information for Resource Management System) Client.
    Fetches near-real-time satellite thermal anomaly detections (VIIRS / MODIS)
    for India and stores them into PostGIS spatial database.
    """

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/country/csv"

    def __init__(self, map_key: Optional[str] = None):
        self.map_key = map_key or os.getenv("FIRMS_MAP_KEY", "").strip()
        self.data_dir = Path(__file__).resolve().parent.parent / "data"

    def fetch_live_hotspots(
        self,
        source: str = "VIIRS_SNPP_NRT",
        country_code: str = "IND",
        days: int = 1,
        timeout: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch near-real-time hotspots from the NASA FIRMS REST API.
        Available sources:
          - VIIRS_SNPP_NRT (375m high resolution - Suomi NPP)
          - VIIRS_NOAA20_NRT (375m - NOAA-20)
          - MODIS_NRT (1km - Terra and Aqua)
        """
        if not self.map_key:
            raise ValueError(
                "FIRMS_MAP_KEY is not set. Please provide a key or set it in .env"
            )

        url = f"{self.BASE_URL}/{self.map_key}/{source}/{country_code}/{days}"
        print(f"[NASA] Querying NASA FIRMS API: {source} for {country_code} (last {days} day(s))...")
        
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        # Check for NASA FIRMS specific error strings returned in body
        text = response.text.strip()
        if "Invalid MAP_KEY" in text:
            raise ValueError("NASA FIRMS returned: Invalid MAP_KEY. Check your key in .env")
        if "Bad Request" in text or "Error:" in text:
            raise ValueError(f"NASA FIRMS API Error: {text}")

        # Parse CSV output
        reader = csv.DictReader(io.StringIO(text))
        hotspots = []
        for row in reader:
            parsed = self._normalize_row(row, default_source=source)
            if parsed:
                hotspots.append(parsed)

        print(f"[SUCCESS] Received {len(hotspots)} thermal anomalies from NASA FIRMS.")
        return hotspots

    def load_sample_hotspots(self) -> List[Dict[str, Any]]:
        """
        Load curated offline sample hotspots across Indian states (Odisha, Punjab,
        Gujarat, Karnataka, Uttarakhand) for testing and offline demonstrations.
        """
        sample_path = self.data_dir / "sample_hotspots_india.json"
        if not sample_path.exists():
            raise FileNotFoundError(f"Sample data file not found at {sample_path}")

        print(f"[LOAD] Loading sample hotspot dataset from: {sample_path.name}...")
        with open(sample_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[SUCCESS] Loaded {len(data)} sample fire records.")
        return data

    def _normalize_row(self, row: Dict[str, Any], default_source: str) -> Optional[Dict[str, Any]]:
        """Clean and convert data types from raw CSV."""
        try:
            lat = float(row.get("latitude", 0))
            lon = float(row.get("longitude", 0))
            if lat == 0 and lon == 0:
                return None

            return {
                "latitude": lat,
                "longitude": lon,
                "scan": float(row["scan"]) if row.get("scan") else None,
                "track": float(row["track"]) if row.get("track") else None,
                "acq_date": row.get("acq_date"),
                "acq_time": row.get("acq_time"),
                "satellite": row.get("satellite", default_source),
                "instrument": row.get("instrument", "VIIRS"),
                "confidence": row.get("confidence", "nominal"),
                "version": row.get("version", "2.0NRT"),
                "bright_ti4": float(row["bright_ti4"]) if row.get("bright_ti4") else None,
                "bright_ti5": float(row["bright_ti5"]) if row.get("bright_ti5") else None,
                "frp": float(row["frp"]) if row.get("frp") else None,
                "daynight": row.get("daynight", "D"),
            }
        except (ValueError, KeyError) as e:
            return None

    def ingest_to_database(
        self,
        hotspots_data: List[Dict[str, Any]],
        db: Optional[Session] = None
    ) -> Dict[str, int]:
        """
        Save parsed hotspot data into PostgreSQL PostGIS table `hotspots`.
        Prevents duplicates by checking (latitude, longitude, acq_date, acq_time).
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        new_count = 0
        skipped_count = 0

        try:
            for item in hotspots_data:
                lat = float(item["latitude"])
                lon = float(item["longitude"])
                acq_date = str(item.get("acq_date", ""))
                acq_time = str(item.get("acq_time", ""))

                # Duplicate detection
                exists = db.query(Hotspot).filter(
                    Hotspot.latitude == lat,
                    Hotspot.longitude == lon,
                    Hotspot.acq_date == acq_date,
                    Hotspot.acq_time == acq_time
                ).first()

                if exists:
                    skipped_count += 1
                    continue

                # Create spatial point geometry (SRID 4326: WGS84 coordinates)
                geom_wkt = f"POINT({lon} {lat})"

                hotspot = Hotspot(
                    latitude=lat,
                    longitude=lon,
                    geom=WKTElement(geom_wkt, srid=4326),
                    scan=item.get("scan"),
                    track=item.get("track"),
                    acq_date=acq_date,
                    acq_time=acq_time,
                    satellite=item.get("satellite"),
                    instrument=item.get("instrument", "VIIRS"),
                    confidence=item.get("confidence"),
                    version=item.get("version"),
                    bright_ti4=item.get("bright_ti4"),
                    bright_ti5=item.get("bright_ti5"),
                    frp=item.get("frp"),
                    daynight=item.get("daynight"),
                    fire_type="unclassified",
                    risk_score=0.0,
                    status="active"
                )
                db.add(hotspot)
                new_count += 1

            db.commit()
            print(f"[DB] Ingestion complete: {new_count} new hotspots inserted, {skipped_count} duplicates skipped.")
            return {
                "total_processed": len(hotspots_data),
                "inserted": new_count,
                "skipped": skipped_count
            }
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_session:
                db.close()

    def run(self, prefer_live: bool = True) -> Dict[str, Any]:
        """
        Execute pipeline:
        1. Attempt live fetch if key is present and prefer_live is True.
        2. Fallback to sample dataset if key is missing or network is unavailable.
        3. Save to database.
        """
        hotspots = []
        source_mode = "sample"

        if prefer_live and self.map_key:
            try:
                hotspots = self.fetch_live_hotspots()
                source_mode = "live_nasa_firms"
            except Exception as e:
                print(f"[WARN] Live fetch failed ({e}). Falling back to offline sample dataset...")
                hotspots = self.load_sample_hotspots()
                source_mode = "sample_fallback"
        else:
            print("[INFO] No FIRMS_MAP_KEY configured. Using bundled Indian sample dataset.")
            hotspots = self.load_sample_hotspots()
            source_mode = "sample"

        ingest_stats = self.ingest_to_database(hotspots)
        return {
            "source": source_mode,
            **ingest_stats
        }


if __name__ == "__main__":
    client = FirmsClient()
    result = client.run()
    print("\n--- Pipeline Execution Summary ---")
    print(json.dumps(result, indent=2))
