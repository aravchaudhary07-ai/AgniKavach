import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Hotspot
from ingestion.spatial_crossref import SpatialCrossReferencer
from ml.classifier import FireClassifier


class RiskScorer:
    """
    Dynamic Threat & Vulnerability Index Calculator for AgniKavach.
    Combines:
      1. Thermal Severity (FRP & Brightness)
      2. Ecological & Canopy Vulnerability (Bhuvan LULC data)
      3. Response Deficit (Distance to nearest Fire Station & Hospital)
      4. Anomaly Category Multiplier (Forest vs. Stubble vs. Industrial Flare)
    Outputs a score from 0.0 to 100.0 with categorical severity tiers:
      - LOW (< 25)
      - MODERATE (25 - 49)
      - HIGH (50 - 74)
      - CRITICAL (>= 75)
    """

    def calculate_score(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the composite risk score for a single enriched hotspot."""
        frp = float(row.get("frp", 15.0) or 15.0)
        bright4 = float(row.get("bright_ti4", 325.0) or 325.0)
        canopy = float(row.get("canopy_cover_pct", 10.0) or 10.0)
        vulnerability_factor = float(row.get("vulnerability_factor", 0.5) or 0.5)
        dist_fire = float(row.get("dist_fire_station_km", 20.0) or 20.0)
        dist_hosp = float(row.get("dist_hospital_km", 20.0) or 20.0)
        fire_type = str(row.get("predicted_fire_type", row.get("fire_type", "unclassified")))
        in_industrial = bool(row.get("in_industrial_baseline", False))

        # 1. Thermal Intensity Component (0 - 35 points)
        # Higher FRP and temperature above 330K increase the rating
        frp_pts = min(25.0, (frp / 60.0) * 25.0)
        temp_pts = min(10.0, max(0.0, (bright4 - 310.0) / 40.0) * 10.0)
        thermal_component = frp_pts + temp_pts

        # 2. Ecological & Canopy Vulnerability Component (0 - 35 points)
        canopy_pts = (canopy / 100.0) * 25.0
        vuln_pts = vulnerability_factor * 10.0
        ecological_component = canopy_pts + vuln_pts

        # 3. Response Deficit / Remoteness Component (0 - 20 points)
        # Fires far from emergency resources pose higher danger of uncontrolled spread
        fire_dist_pts = min(12.0, (dist_fire / 40.0) * 12.0)
        hosp_dist_pts = min(8.0, (dist_hosp / 50.0) * 8.0)
        response_deficit = fire_dist_pts + hosp_dist_pts

        # 4. Raw Cumulative Score (0 - 90 base) + Confidence baseline (0 - 10)
        base_score = thermal_component + ecological_component + response_deficit + 5.0

        # 5. Fire Type Risk Multiplier
        if in_industrial or fire_type == "industrial_flare":
            # Normal industrial operation: suppress risk unless FRP is massive (> 90 MW)
            if frp < 80.0:
                final_score = min(22.0, base_score * 0.22) # Stays in LOW tier
            else:
                final_score = min(58.0, base_score * 0.60) # Possible flare anomaly
        elif fire_type == "crop_burn":
            # Crop stubble burning: moderate risk tier
            final_score = min(48.0, max(28.0, base_score * 0.65 + 10.0))
        elif fire_type == "forest_fire":
            # Forest fire: full threat multiplier
            final_score = min(100.0, base_score * 1.05)
        elif fire_type == "false_alarm":
            final_score = min(15.0, base_score * 0.15)
        else:
            final_score = min(100.0, base_score)

        final_score = round(max(5.0, min(100.0, final_score)), 1)

        # Categorical Severity Tier
        if final_score >= 75.0:
            severity = "CRITICAL"
            action_recommended = "Immediate Multi-Station Dispatch + Hospital Trauma Alert"
        elif final_score >= 50.0:
            severity = "HIGH"
            action_recommended = "Primary Fire Brigade Dispatch + Medical Standby"
        elif final_score >= 25.0:
            severity = "MODERATE"
            action_recommended = "Agricultural Officer Notification & Stubble Burn Advisory"
        else:
            severity = "LOW"
            action_recommended = "Routine Industrial Flare / Controlled Heat (No Emergency Alert Needed)"

        return {
            "risk_score": final_score,
            "severity_tier": severity,
            "action_recommended": action_recommended,
            "thermal_component": round(thermal_component, 1),
            "ecological_component": round(ecological_component, 1),
            "response_deficit": round(response_deficit, 1)
        }

    def score_active_hotspots(self) -> pd.DataFrame:
        """
        Runs full classification and risk scoring on all PostgreSQL database hotspots,
        and saves risk_score and status to the database.
        """
        classifier = FireClassifier()
        classified_df = classifier.classify_database_hotspots()

        scores = []
        db = SessionLocal()
        try:
            for _, row in classified_df.iterrows():
                h_id = int(row["hotspot_id"])
                res = self.calculate_score(row.to_dict())
                scores.append(res)

                # Persist to database
                db.query(Hotspot).filter(Hotspot.id == h_id).update({
                    Hotspot.risk_score: res["risk_score"],
                    Hotspot.status: "active" if res["severity_tier"] in ["CRITICAL", "HIGH"] else "monitored"
                })
            db.commit()
            print(f"[DB] Updated {len(scores)} hotspots with dynamic risk scores in PostgreSQL.")
        finally:
            db.close()

        # Merge results into output DataFrame
        score_df = pd.DataFrame(scores)
        result = pd.concat([classified_df.reset_index(drop=True), score_df.reset_index(drop=True)], axis=1)
        return result


if __name__ == "__main__":
    scorer = RiskScorer()
    print("\n--- Computing Dynamic Threat & Vulnerability Index ---")
    final_df = scorer.score_active_hotspots()

    summary_cols = [
        "hotspot_id", "land_cover_type", "predicted_fire_type", 
        "frp", "risk_score", "severity_tier", "action_recommended"
    ]
    print(final_df[summary_cols].to_string(index=False))
