import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database.connection import get_db, SessionLocal
from database.models import Hotspot, Infrastructure, IndustrialBaseline, AlertHistory
from routing.osrm_client import OSRMClient
from routing.alert_service import AlertService
from ingestion.firms_client import FirmsClient
from ml.risk_scorer import RiskScorer


app = FastAPI(
    title="AgniKavach API",
    description="Intelligent Autonomous Wildfire & Thermal Anomaly Early Warning and Rapid Response System",
    version="1.0.0"
)

# Enable CORS for local dev and cross-origin frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

osrm_client = OSRMClient()
alert_service = AlertService()


@app.get("/api/health")
def health_check():
    return {"status": "ONLINE", "system": "AgniKavach Geospatial Server", "database": "PostgreSQL + PostGIS"}


@app.get("/api/incidents")
def get_incidents(
    tier: Optional[str] = None,
    fire_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieve all active thermal incidents with risk scores and classification."""
    query = db.query(Hotspot).order_by(desc(Hotspot.risk_score))
    
    if fire_type:
        query = query.filter(Hotspot.fire_type == fire_type)

    hotspots = query.all()
    results = []

    for h in hotspots:
        score = h.risk_score or 0.0
        if score >= 75.0:
            severity = "CRITICAL"
        elif score >= 50.0:
            severity = "HIGH"
        elif score >= 25.0:
            severity = "MODERATE"
        else:
            severity = "LOW"

        if tier and severity.lower() != tier.lower():
            continue

        # Find closest fire station
        closest_fire = (
            db.query(
                Infrastructure.name,
                (func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h.longitude, h.latitude), 4326)) / 1000.0).label("dist_km"),
                Infrastructure.contact_phone
            )
            .filter(Infrastructure.type == "fire_station")
            .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h.longitude, h.latitude), 4326)))
            .first()
        )

        # Find closest hospital
        closest_hospital = (
            db.query(
                Infrastructure.name,
                (func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h.longitude, h.latitude), 4326)) / 1000.0).label("dist_km"),
                Infrastructure.contact_phone
            )
            .filter(Infrastructure.type == "hospital")
            .order_by(func.ST_DistanceSphere(Infrastructure.geom, func.ST_SetSRID(func.ST_MakePoint(h.longitude, h.latitude), 4326)))
            .first()
        )

        results.append({
            "id": h.id,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "frp": h.frp,
            "brightness": h.bright_ti4 or h.brightness,
            "acq_date": h.acq_date,
            "acq_time": h.acq_time,
            "satellite": h.satellite,
            "instrument": h.instrument,
            "confidence": h.confidence,
            "fire_type": h.fire_type,
            "risk_score": h.risk_score,
            "severity_tier": severity,
            "status": h.status,
            "nearest_fire_station": {
                "name": closest_fire[0] if closest_fire else None,
                "distance_km": round(float(closest_fire[1]), 1) if closest_fire else None,
                "contact_phone": closest_fire[2] if closest_fire else None
            },
            "nearest_hospital": {
                "name": closest_hospital[0] if closest_hospital else None,
                "distance_km": round(float(closest_hospital[1]), 1) if closest_hospital else None,
                "contact_phone": closest_hospital[2] if closest_hospital else None
            }
        })

    return {"count": len(results), "incidents": results}


@app.get("/api/infrastructure")
def get_infrastructure(db: Session = Depends(get_db)):
    """Retrieve all emergency response stations and medical facilities."""
    items = db.query(Infrastructure).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "type": item.type,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "capacity": item.capacity,
            "contact_phone": item.contact_phone,
            "address": item.address
        }
        for item in items
    ]


@app.get("/api/baselines")
def get_baselines(db: Session = Depends(get_db)):
    """Retrieve known industrial heat baseline zones and buffer perimeters."""
    baselines = db.query(IndustrialBaseline).all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "category": b.category,
            "latitude": b.latitude,
            "longitude": b.longitude,
            "buffer_radius_m": b.buffer_radius_m,
            "typical_frp_threshold": b.typical_frp_threshold,
            "notes": b.notes
        }
        for b in baselines
    ]


@app.get("/api/routes/{incident_id}")
def get_incident_routes(incident_id: int, db: Session = Depends(get_db)):
    """Compute and return multi-agency GeoJSON turn-by-turn routes (Fire Brigade + Hospital)."""
    try:
        return osrm_client.compute_multi_agency_routes(incident_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/alerts")
def get_alerts_history(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve audit history of dispatched emergency notifications."""
    alerts = (
        db.query(AlertHistory)
        .order_by(desc(AlertHistory.dispatched_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "hotspot_id": a.hotspot_id,
            "station_id": a.station_id,
            "recipient_contact": a.recipient_contact,
            "alert_type": a.alert_type,
            "status": a.status,
            "distance_km": a.distance_km,
            "eta_minutes": a.eta_minutes,
            "message_body": a.message_body,
            "dispatched_at": a.dispatched_at.isoformat() if a.dispatched_at else None
        }
        for a in alerts
    ]


@app.post("/api/pipeline/run")
def trigger_full_pipeline():
    """Trigger data ingestion, spatial enrichment, ML classification, and risk scoring."""
    firms = FirmsClient()
    firms_res = firms.run()

    scorer = RiskScorer()
    scored_df = scorer.score_active_hotspots()

    return {
        "status": "SUCCESS",
        "ingestion": firms_res,
        "scored_incidents_count": len(scored_df)
    }


@app.post("/api/dispatch/{incident_id}")
def trigger_incident_dispatch(incident_id: int, db: Session = Depends(get_db)):
    """Manually dispatch alerts for a specific incident."""
    hotspot = db.query(Hotspot).filter(Hotspot.id == incident_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Incident not found")

    routes = osrm_client.compute_multi_agency_routes(incident_id, db)
    fb = routes.get("fire_brigade_route")
    med = routes.get("medical_ambulance_route")

    dispatched = []
    if fb:
        msg = alert_service.format_fire_alert(hotspot, fb)
        res = alert_service.dispatch_alert(
            recipient=fb["contact_phone"] or alert_service.default_recipient,
            message=msg,
            hotspot_id=hotspot.id,
            station_id=fb["station_id"],
            alert_type="FIRE_BRIGADE_MANUAL_SMS",
            distance_km=fb["distance_km"],
            eta_minutes=fb["duration_minutes"],
            db=db
        )
        dispatched.append(res)

    if med:
        msg = alert_service.format_medical_alert(hotspot, med)
        res = alert_service.dispatch_alert(
            recipient=med["contact_phone"] or alert_service.default_recipient,
            message=msg,
            hotspot_id=hotspot.id,
            station_id=med["hospital_id"],
            alert_type="HOSPITAL_TRAUMA_MANUAL_SMS",
            distance_km=med["distance_km"],
            eta_minutes=med["duration_minutes"],
            db=db
        )
        dispatched.append(res)

    return {"incident_id": incident_id, "dispatched_alerts": dispatched}


# Serve Web-GIS Frontend directly at root
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(WEB_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
