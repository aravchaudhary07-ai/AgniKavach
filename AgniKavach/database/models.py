from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, ForeignKey, func
)
from geoalchemy2 import Geometry
from database.connection import Base


class Hotspot(Base):
    __tablename__ = "hotspots"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    
    # NASA FIRMS Telemetry Fields
    brightness = Column(Float, nullable=True)
    scan = Column(Float, nullable=True)
    track = Column(Float, nullable=True)
    acq_date = Column(String(20), nullable=True)
    acq_time = Column(String(10), nullable=True)
    satellite = Column(String(50), nullable=True)
    instrument = Column(String(50), nullable=True)
    confidence = Column(String(20), nullable=True)
    version = Column(String(20), nullable=True)
    bright_ti4 = Column(Float, nullable=True)
    bright_ti5 = Column(Float, nullable=True)
    frp = Column(Float, nullable=True) # Fire Radiative Power (MW)
    daynight = Column(String(5), nullable=True)

    # Multi-Modal ML Classification & Risk Assessment
    fire_type = Column(String(50), default="unclassified") # forest_fire, crop_burn, industrial, false_alarm
    risk_score = Column(Float, default=0.0) # 0.0 to 100.0
    status = Column(String(30), default="active") # active, under_investigation, contained, false_positive
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Infrastructure(Base):
    __tablename__ = "infrastructure"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False) # fire_station, hospital, industrial_zone, forest_beat
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    
    capacity = Column(Integer, default=1) # e.g. number of fire tenders
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IndustrialBaseline(Base):
    __tablename__ = "industrial_baselines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False) # refinery, steel_plant, power_plant, brick_kiln
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    buffer_radius_m = Column(Float, default=1500.0) # Buffer radius in meters
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)
    typical_frp_threshold = Column(Float, default=30.0)
    notes = Column(Text, nullable=True)


class AlertHistory(Base):
    __tablename__ = "alerts_history"

    id = Column(Integer, primary_key=True, index=True)
    hotspot_id = Column(Integer, ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("infrastructure.id", ondelete="SET NULL"), nullable=True)
    
    recipient_contact = Column(String(100), nullable=False)
    alert_type = Column(String(20), default="SMS") # SMS, EMAIL, WEBHOOK, DASHBOARD
    status = Column(String(20), default="SENT") # SENT, FAILED, PENDING
    
    distance_km = Column(Float, nullable=True)
    eta_minutes = Column(Float, nullable=True)
    message_body = Column(Text, nullable=False)
    
    dispatched_at = Column(DateTime(timezone=True), server_default=func.now())
