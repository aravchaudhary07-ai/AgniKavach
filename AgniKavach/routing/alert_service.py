import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy.orm import Session
from twilio.rest import Client as TwilioClient

from database.connection import SessionLocal
from database.models import Hotspot, Infrastructure, AlertHistory
from routing.osrm_client import OSRMClient


class AlertService:
    """
    Automated Multi-Agency Emergency Alert Dispatcher.
    Dispatches:
      1. Fire Brigade Deployment Alerts (Fire Tenders, Equipment, Turn-by-Turn Route)
      2. Medical Emergency & Hospital Trauma Readiness Alerts (Burn/Smoke Units, Ambulance Routing)
    Persists audit records into PostgreSQL table `alerts_history`.
    """

    def __init__(self):
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        self.twilio_phone = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
        self.default_recipient = os.getenv("EMERGENCY_ALERT_RECIPIENT", "+91-9876543210").strip()
        
        self.osrm = OSRMClient()
        self.twilio_client = None
        if self.twilio_sid and self.twilio_token:
            try:
                self.twilio_client = TwilioClient(self.twilio_sid, self.twilio_token)
            except Exception as e:
                print(f"[WARN] Twilio initialization failed ({e}). Running in simulation mode.")

    def format_fire_alert(
        self,
        hotspot: Hotspot,
        fire_route: Dict[str, Any]
    ) -> str:
        """Construct emergency dispatch message for Fire Services."""
        maps_link = f"https://www.google.com/maps/dir/?api=1&origin={fire_route['station_coordinates'][0]},{fire_route['station_coordinates'][1]}&destination={hotspot.latitude},{hotspot.longitude}"
        return (
            f"[AGNI-KAVACH FIRE DISPATCH ALERT]\n"
            f"SEVERITY: {hotspot.status.upper()} | RISK SCORE: {hotspot.risk_score}/100\n"
            f"TYPE: {hotspot.fire_type.replace('_', ' ').title()}\n"
            f"COORDINATES: {hotspot.latitude:.4f} N, {hotspot.longitude:.4f} E\n"
            f"INTENSITY: {hotspot.frp} MW Fire Radiative Power\n"
            f"STATION: {fire_route['station_name']}\n"
            f"DISTANCE: {fire_route['distance_km']} km | ETA: {fire_route['duration_minutes']} mins\n"
            f"ROUTE: {maps_link}\n"
            f"ACTION: Immediate deployment of emergency response unit required."
        )

    def format_medical_alert(
        self,
        hotspot: Hotspot,
        med_route: Dict[str, Any]
    ) -> str:
        """Construct hospital casualty and trauma readiness warning (Task 4.3)."""
        maps_link = f"https://www.google.com/maps/dir/?api=1&origin={hotspot.latitude},{hotspot.longitude}&destination={med_route['hospital_coordinates'][0]},{med_route['hospital_coordinates'][1]}"
        return (
            f"[AGNI-KAVACH HOSPITAL READINESS WARNING]\n"
            f"PRIORITY: HIGH-PRIORITY MEDICAL EVACUATION ALERT\n"
            f"FACILITY: {med_route['hospital_name']}\n"
            f"INCIDENT: {hotspot.fire_type.replace('_', ' ').title()} near ({hotspot.latitude:.4f}, {hotspot.longitude:.4f})\n"
            f"DISTANCE: {med_route['distance_km']} km | AMBULANCE TIME: {med_route['duration_minutes']} mins\n"
            f"HAZARDS: Acute smoke inhalation, respiratory distress, thermal burn trauma\n"
            f"RECOMMENDATION: Put Trauma & Burn Care units on active standby; mobilize 2 field ambulances.\n"
            f"AMBULANCE PATH: {maps_link}"
        )

    def dispatch_alert(
        self,
        recipient: str,
        message: str,
        hotspot_id: int,
        station_id: Optional[int],
        alert_type: str,
        distance_km: float,
        eta_minutes: float,
        db: Session
    ) -> Dict[str, Any]:
        """Send alert via SMS (or simulated gateway) and record in database."""
        status = "SENT"
        
        if self.twilio_client and self.twilio_phone and recipient.startswith("+"):
            try:
                self.twilio_client.messages.create(
                    body=message,
                    from_=self.twilio_phone,
                    to=recipient
                )
                status = "SENT"
            except Exception as e:
                print(f"[WARN] Failed to send live SMS via Twilio ({e}). Logging as SIMULATED.")
                status = "SIMULATED"
        else:
            status = "SIMULATED"

        # Record in PostgreSQL alerts_history audit table
        audit = AlertHistory(
            hotspot_id=hotspot_id,
            station_id=station_id,
            recipient_contact=recipient,
            alert_type=alert_type,
            status=status,
            distance_km=distance_km,
            eta_minutes=eta_minutes,
            message_body=message
        )
        db.add(audit)
        db.commit()

        return {
            "hotspot_id": hotspot_id,
            "recipient": recipient,
            "alert_type": alert_type,
            "status": status,
            "distance_km": distance_km,
            "eta_minutes": eta_minutes
        }

    def process_and_dispatch_active_incidents(
        self,
        min_risk_score: float = 60.0
    ) -> List[Dict[str, Any]]:
        """
        Scans database for high-risk active fire incidents and triggers
        both Fire Brigade and Medical Trauma alert dispatches.
        """
        db = SessionLocal()
        dispatched_summary = []

        try:
            # Query active high-risk incidents (forest fires or high severity)
            high_risk_hotspots = (
                db.query(Hotspot)
                .filter(Hotspot.risk_score >= min_risk_score)
                .order_by(Hotspot.risk_score.desc())
                .all()
            )

            print(f"[DISPATCH] Scanning incidents with Risk Score >= {min_risk_score}... Found {len(high_risk_hotspots)}.")

            for h in high_risk_hotspots:
                print(f"\n[DISPATCH] Processing Incident #{h.id} ({h.fire_type}, Risk: {h.risk_score}/100)...")
                routes = self.osrm.compute_multi_agency_routes(h.id, db)

                fb = routes.get("fire_brigade_route")
                med = routes.get("medical_ambulance_route")

                # 1. Fire Brigade Dispatch
                if fb:
                    fb_msg = self.format_fire_alert(h, fb)
                    fb_res = self.dispatch_alert(
                        recipient=fb["contact_phone"] or self.default_recipient,
                        message=fb_msg,
                        hotspot_id=h.id,
                        station_id=fb["station_id"],
                        alert_type="FIRE_BRIGADE_SMS",
                        distance_km=fb["distance_km"],
                        eta_minutes=fb["duration_minutes"],
                        db=db
                    )
                    dispatched_summary.append(fb_res)
                    print(f"  🚒 Fire Alert Dispatched -> {fb['station_name']} ({fb['distance_km']} km, ETA: {fb['duration_minutes']}m)")

                # 2. Medical Help & Hospital Readiness Alert (Task 4.3)
                if med:
                    med_msg = self.format_medical_alert(h, med)
                    med_res = self.dispatch_alert(
                        recipient=med["contact_phone"] or self.default_recipient,
                        message=med_msg,
                        hotspot_id=h.id,
                        station_id=med["hospital_id"],
                        alert_type="HOSPITAL_TRAUMA_SMS",
                        distance_km=med["distance_km"],
                        eta_minutes=med["duration_minutes"],
                        db=db
                    )
                    dispatched_summary.append(med_res)
                    print(f"  🏥 Medical Alert Dispatched -> {med['hospital_name']} ({med['distance_km']} km, ETA: {med['duration_minutes']}m)")

            return dispatched_summary
        finally:
            db.close()


if __name__ == "__main__":
    service = AlertService()
    print("=== RUNNING AGNI-KAVACH EMERGENCY DISPATCH TEST ===")
    results = service.process_and_dispatch_active_incidents(min_risk_score=60.0)
    
    print("\n--- Summary of Dispatched Alerts Recorded in PostgreSQL ---")
    for r in results:
        print(f"  [DISPATCHED] Incident #{r['hotspot_id']} | Type: {r['alert_type']} | To: {r['recipient']} | Status: {r['status']}")
