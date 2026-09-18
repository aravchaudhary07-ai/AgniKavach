import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Union
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class FeaturePipeline:
    """
    Feature Engineering Pipeline for Fire Incident Classification.
    Transforms raw satellite telemetry and spatial cross-referencing context
    into numerical feature vectors for LightGBM.
    """

    FEATURE_COLUMNS = [
        "bright_ti4",
        "bright_ti5",
        "bright_diff",
        "frp",
        "canopy_cover_pct",
        "vulnerability_factor",
        "dist_fire_station_km",
        "dist_hospital_km",
        "in_industrial_baseline",
        "confidence_score",
        "is_night",
        "is_forest",
        "is_cropland",
        "is_industrial"
    ]

    CONFIDENCE_MAP = {
        "low": 1.0,
        "l": 1.0,
        "nominal": 2.0,
        "n": 2.0,
        "high": 3.0,
        "h": 3.0
    }

    def transform_single(self, row: Dict[str, Any]) -> pd.DataFrame:
        """Transform a single enriched hotspot dictionary into a feature dataframe."""
        return self.transform_batch(pd.DataFrame([row]))

    def transform_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineers thermal, temporal, and spatial features across a DataFrame.
        """
        out = pd.DataFrame(index=df.index)

        # Thermal Telemetry Features
        bright4 = pd.to_numeric(df.get("bright_ti4"), errors="coerce").fillna(325.0)
        bright5 = pd.to_numeric(df.get("bright_ti5"), errors="coerce").fillna(295.0)
        out["bright_ti4"] = bright4
        out["bright_ti5"] = bright5
        out["bright_diff"] = bright4 - bright5

        out["frp"] = pd.to_numeric(df.get("frp"), errors="coerce").fillna(15.0)

        # Spatial Context Features
        out["canopy_cover_pct"] = pd.to_numeric(df.get("canopy_cover_pct"), errors="coerce").fillna(10.0)
        out["vulnerability_factor"] = pd.to_numeric(df.get("vulnerability_factor"), errors="coerce").fillna(0.5)
        out["dist_fire_station_km"] = pd.to_numeric(df.get("dist_fire_station_km"), errors="coerce").fillna(50.0)
        out["dist_hospital_km"] = pd.to_numeric(df.get("dist_hospital_km"), errors="coerce").fillna(50.0)

        # Baseline & Category Flags
        in_baseline = df.get("in_industrial_baseline", False).astype(bool)
        out["in_industrial_baseline"] = in_baseline.astype(int)

        # Ordinal Confidence Mapping
        conf_series = df.get("confidence", "nominal").astype(str).str.lower()
        out["confidence_score"] = conf_series.map(self.CONFIDENCE_MAP).fillna(2.0)

        # Day / Night Binary
        daynight = df.get("daynight", "D").astype(str).str.upper()
        out["is_night"] = (daynight == "N").astype(int)

        # One-Hot Encoding for Land-Cover
        land_type = df.get("land_cover_type", "scrub").astype(str).str.lower()
        out["is_forest"] = (land_type == "forest").astype(int)
        out["is_cropland"] = (land_type == "cropland").astype(int)
        out["is_industrial"] = (land_type == "industrial").astype(int)

        return out[self.FEATURE_COLUMNS]


if __name__ == "__main__":
    from ingestion.spatial_crossref import SpatialCrossReferencer
    
    print("[TEST] Running Feature Engineering Pipeline on active database hotspots...")
    engine = SpatialCrossReferencer()
    enriched_df = engine.enrich_active_hotspots()
    
    pipeline = FeaturePipeline()
    feature_df = pipeline.transform_batch(enriched_df)
    
    print("\n[SUCCESS] Extracted ML Features Shape:", feature_df.shape)
    print(feature_df.head().to_string())
