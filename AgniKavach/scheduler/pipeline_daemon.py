import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import schedule

from ingestion.firms_client import FirmsClient
from ingestion.spatial_crossref import SpatialCrossReferencer
from ml.risk_scorer import RiskScorer
from ml.visual_verifier import VisualVerifier
from routing.alert_service import AlertService


class PipelineDaemon:
    """
    AgniKavach Master Automation Daemon.
    Continuously orchestrates:
      1. Satellite Hotspot Ingestion (NASA FIRMS)
      2. Spatial Cross-Referencing (GeoPandas + PostGIS)
      3. AI Classification & Threat Scoring (LightGBM)
      4. Optical Visual Verification (Sentinel-2 Deep CNN)
      5. Multi-Agency Emergency Dispatch (Fire Stations & Hospital Trauma Centers)
    """

    def __init__(self, min_risk_score: float = 75.0, skip_optical: bool = False):
        self.min_risk_score = min_risk_score
        self.skip_optical = skip_optical
        
        self.firms_client = FirmsClient()
        self.cross_ref = SpatialCrossReferencer()
        self.risk_scorer = RiskScorer()
        self.visual_verifier = VisualVerifier()
        self.alert_service = AlertService()

    def run_pipeline_cycle(self) -> Dict[str, Any]:
        """Execute one complete cycle of the multi-modal detection & response pipeline."""
        start_time = datetime.now()
        timestamp_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n=======================================================")
        print(f" 🔥 AGNI-KAVACH PIPELINE CYCLE STARTED [{timestamp_str}]")
        print(f"=======================================================")

        summary = {
            "timestamp": timestamp_str,
            "status": "SUCCESS",
            "steps": {}
        }

        try:
            # -------------------------------------------------------------
            # STEP 1: Satellite Ingestion (NASA FIRMS)
            # -------------------------------------------------------------
            print("\n[STEP 1/5] Ingesting Satellite Thermal Telemetry...")
            ingest_res = self.firms_client.run()
            summary["steps"]["ingestion"] = {
                "source": ingest_res.get("source"),
                "inserted": ingest_res.get("inserted", 0),
                "skipped_duplicate": ingest_res.get("skipped_duplicate", 0)
            }
            print(f"  -> Ingested: {ingest_res.get('inserted', 0)} new, Skipped: {ingest_res.get('skipped_duplicate', 0)} duplicates")

            # -------------------------------------------------------------
            # STEP 2: Spatial Cross-Referencing & Enrichment
            # -------------------------------------------------------------
            print("\n[STEP 2/5] Cross-Referencing Geospatial Boundaries & Infrastructure...")
            enriched_df = self.cross_ref.enrich_active_hotspots()
            summary["steps"]["spatial_enrichment"] = {
                "hotspots_enriched": len(enriched_df)
            }
            print(f"  -> Spatial Context Derived for {len(enriched_df)} Hotspots")

            # -------------------------------------------------------------
            # STEP 3: Multi-Modal AI Classification & Risk Scoring
            # -------------------------------------------------------------
            print("\n[STEP 3/5] Running LightGBM Classifier & Dynamic Threat Index...")
            scored_df = self.risk_scorer.score_active_hotspots()
            critical_count = len(scored_df[scored_df["severity_tier"] == "CRITICAL"])
            high_count = len(scored_df[scored_df["severity_tier"] == "HIGH"])
            summary["steps"]["ai_scoring"] = {
                "total_scored": len(scored_df),
                "critical": critical_count,
                "high": high_count
            }
            print(f"  -> Scored {len(scored_df)} Incidents | Critical: {critical_count} | High: {high_count}")

            # -------------------------------------------------------------
            # STEP 4: Optical Verification (Sentinel-2 Deep CNN)
            # -------------------------------------------------------------
            if not self.skip_optical:
                print("\n[STEP 4/5] Running Sentinel-2 Optical CNN Visual Verification...")
                optical_results = self.visual_verifier.run_verification_on_hotspots()
                confirmed_count = sum(1 for r in optical_results if r.get("visual_confirmation"))
                summary["steps"]["optical_verification"] = {
                    "verified_hotspots": len(optical_results),
                    "visually_confirmed_active": confirmed_count
                }
                print(f"  -> Optical Analysis Complete: {confirmed_count}/{len(optical_results)} Visually Confirmed")
            else:
                print("\n[STEP 4/5] Skipping Optical CNN (skip_optical flag enabled).")
                summary["steps"]["optical_verification"] = "SKIPPED"

            # -------------------------------------------------------------
            # STEP 5: Multi-Agency Routing & Emergency Alert Dispatch
            # -------------------------------------------------------------
            print(f"\n[STEP 5/5] Checking Incidents for Emergency Dispatch (Risk >= {self.min_risk_score})...")
            dispatched = self.alert_service.process_and_dispatch_active_incidents(
                min_risk_score=self.min_risk_score
            )
            summary["steps"]["alert_dispatch"] = {
                "dispatches_transmitted": len(dispatched),
                "incidents_notified": len(set(d["hotspot_id"] for d in dispatched)) if dispatched else 0
            }
            print(f"  -> Dispatched {len(dispatched)} emergency transmissions to Fire & Medical authorities")

        except Exception as e:
            print(f"[ERROR] Pipeline cycle encountered an exception: {e}")
            summary["status"] = "FAILED"
            summary["error"] = str(e)

        elapsed = (datetime.now() - start_time).total_seconds()
        summary["duration_seconds"] = round(elapsed, 2)
        print(f"\n=======================================================")
        print(f" ✅ CYCLE FINISHED in {elapsed:.2f}s | STATUS: {summary['status']}")
        print(f"=======================================================\n")
        return summary

    def start_daemon(self, interval_minutes: int = 5):
        """Start recurring background automation daemon using schedule."""
        print(f"[*] Starting AgniKavach Autonomous Daemon.")
        print(f"[*] Schedule interval: Every {interval_minutes} minute(s)")
        print(f"[*] Minimum dispatch threshold: Risk Score >= {self.min_risk_score}")
        print(f"[*] Press Ctrl+C to terminate daemon at any time.\n")

        # Execute immediately on start
        self.run_pipeline_cycle()

        # Register recurring schedule
        schedule.every(interval_minutes).minutes.do(self.run_pipeline_cycle)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[INFO] Daemon stopped by operator. Exiting gracefully.")


def parse_args():
    parser = argparse.ArgumentParser(description="AgniKavach Autonomous Pipeline Daemon")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in minutes for continuous daemon mode (default: 5)"
    )
    parser.add_argument(
        "--min-risk",
        type=float,
        default=75.0,
        help="Minimum risk score threshold to trigger emergency dispatches (default: 75.0)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single pipeline cycle and exit immediately (one-shot mode)"
    )
    parser.add_argument(
        "--skip-optical",
        action="store_true",
        help="Skip Sentinel-2 PyTorch CNN verification step"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    daemon = PipelineDaemon(
        min_risk_score=args.min_risk,
        skip_optical=args.skip_optical
    )

    if args.once:
        daemon.run_pipeline_cycle()
    else:
        daemon.start_daemon(interval_minutes=args.interval)
