# 🔥 AgniKavach (अग्निकवच)
> **Autonomous Multi-Modal Wildfire & Thermal Anomaly Early Warning and Rapid Response System**  
> *Smart India Hackathon (SIH) — Problem Statement ID: 26162*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-PostGIS-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LightGBM](https://img.shields.io/badge/LightGBM-ML_Engine-FF6F00?style=for-the-badge)](https://lightgbm.readthedocs.io/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-Spatial_Analysis-139C5A?style=for-the-badge)](https://geopandas.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.style=for-the-badge)](LICENSE)

---

## 📌 Executive Summary

**AgniKavach** is an end-to-end, intelligent geo-spatial disaster mitigation platform engineered to solve the critical challenges in wildfire and thermal anomaly response. By fusing near-real-time satellite feeds with rich open infrastructure data, historical heat baselines, and multi-modal AI classification, AgniKavach autonomously:

1. **Detects** thermal anomalies with high-cadence satellite telemetry (NASA FIRMS / VIIRS / MODIS, Sentinel-2, Bhuvan-NRSC).
2. **Filters & Categorizes** fire incidents using machine learning (differentiating forest fires from agricultural stubble burns, industrial flaring, and false positives).
3. **Calculates Dynamic Risk Scores** factoring in land cover, population density, wind parameters, and proximity to critical assets.
4. **Calculates Fastest Emergency Routes** using Open Source Routing Machine (OSRM) to dispatch the closest emergency response stations.
5. **Autonomously Dispatches Alerts** via SMS/Email to district forest officers, disaster management teams, and nearby emergency personnel without requiring manual intervention.
6. **Visualizes Active Incidents** on an interactive, operator-grade Web-GIS command dashboard.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Data_Ingestion ["1. Data Ingestion & Harvesting"]
        A1[NASA FIRMS API<br/>VIIRS / MODIS Hotspots]
        A2[Bhuvan-NRSC<br/>Indian Geospatial Layers]
        A3[OpenStreetMap<br/>Roads, Fire Stations, Industries]
        A4[WorldPop<br/>Population Density Grids]
    end

    subgraph Spatial_Fusion ["2. Spatial Fusion & Baseline Filtering"]
        B1[(PostgreSQL + PostGIS)]
        B2[Baseline Heat Signature Filter<br/>Flags Known Industrial Zones]
        B3[Spatial Cross-Referencing<br/>GeoPandas / Shapely]
    end

    subgraph AI_Engine ["3. Multi-Modal AI & Risk Assessment"]
        C1[Feature Engineering<br/>FRP, Temp, Proximity, Land Cover]
        C2[LightGBM Classifier<br/>Forest vs Crop vs Industrial vs False Alarm]
        C3[Dynamic Vulnerability Scoring<br/>Threat Index Calculation]
    end

    subgraph Rapid_Response ["4. Autonomous Response & Dispatch"]
        D1[OSRM Emergency Routing<br/>Optimal Station-to-Fire Path]
        D2[Twilio Alert Gateway<br/>Automated SMS & Email Broadcast]
    end

    subgraph Presentation ["5. Command & Control"]
        E1[FastAPI High-Performance Backend]
        E2[Web-GIS Real-Time Dashboard<br/>React + Leaflet / MapLibre]
    end

    A1 & A2 & A3 & A4 --> B1
    B1 --> B2 --> B3
    B3 --> C1 --> C2 --> C3
    C3 -->|High Severity Incident| D1 & D2
    B1 & C3 & D1 --> E1 --> E2
```

---

## ⚡ Key Capabilities & Innovation

| Capability | Description |
|---|---|
| 🛰️ **Multi-Source Satellite Fusion** | Continuous ingestion of high-resolution thermal hotspot feeds from NASA FIRMS (VIIRS 375m & MODIS 1km) and Indian Bhuvan datasets. |
| 🛡️ **Zero-False-Alarm Baseline Engine** | Cross-references detected thermal signatures against historical industrial heat zones (steel plants, refineries, brick kilns) to eliminate false dispatches. |
| 🧠 **Intelligent Fire Classification** | Trained **LightGBM** gradient boosted decision trees classify anomaly types based on Fire Radiative Power (FRP), brightness temperature, seasonal agricultural calendars, and land-use context. |
| 📍 **Dynamic Threat & Vulnerability Index** | Calculates multi-factor risk scores combining fire intensity, distance to vulnerable settlements (WorldPop), critical infrastructure, and dense forest canopies. |
| 🚒 **Automated Multi-Station Routing** | Integrates **OSRM** to automatically identify the nearest active fire stations, calculate turn-by-turn routes, and estimate time of arrival (ETA). |
| 🚨 **Zero-Human-Delay Alerts** | Background automation scheduler triggers real-time alerts with direct map coordinates and route links via SMS and email. |
| 🌐 **Interactive Web-GIS Command Center** | Intuitive operator dashboard featuring live heatmaps, incident queues, fire spread trajectories, and resource allocation statuses. |

---

## 📂 Project Structure

```
c:/_SIH/
├── README.md                     # Project documentation & architecture overview
├── .gitignore                    # Git exclusion rules
│
└── AgniKavach/
    ├── requirements.txt          # Python dependencies
    ├── venv/                     # Local Python virtual environment
    │
    ├── ingestion/                # (Phase 2) Data scrapers & ingestion modules
    │   ├── firms_client.py       # NASA FIRMS API fetcher
    │   ├── osm_loader.py         # OpenStreetMap infrastructure parser
    │   └── bhuvan_ingest.py      # Bhuvan & land-use boundary processor
    │
    ├── database/                 # (Phase 1) Database schema & ORM models
    │   ├── connection.py         # SQLAlchemy & PostGIS connection pool
    │   └── models.py             # Hotspot, Station, Alert tables
    │
    ├── ml/                       # (Phase 3) Machine learning & risk evaluation
    │   ├── feature_pipeline.py   # Spatial & thermal feature extractor
    │   ├── classifier.py         # LightGBM fire type classifier
    │   └── risk_scorer.py        # Threat index & vulnerability calculator
    │
    ├── routing/                  # (Phase 4) Route calculation & dispatcher
    │   ├── osrm_client.py        # OSRM emergency routing engine
    │   └── alert_service.py      # Twilio SMS / Email dispatcher
    │
    ├── api/                      # (Phase 5) FastAPI backend service
    │   ├── main.py               # API application entry point
    │   └── routes/               # API endpoints (incidents, routes, telemetry)
    │
    └── scheduler/                # (Phase 6) Master automation daemon
        └── pipeline_daemon.py    # Background task scheduler
```

---

## 🛠️ Technology Stack

- **Core Language:** Python 3.11+
- **Spatial Database:** PostgreSQL 16 + PostGIS Extension
- **Spatial Analytics:** GeoPandas, Shapely, PyProj, PyOgrio
- **Machine Learning:** LightGBM, Scikit-Learn, NumPy, Pandas
- **Backend API:** FastAPI, Uvicorn, SQLAlchemy 2.0, GeoAlchemy2
- **Routing Engine:** OSRM (Open Source Routing Machine)
- **Communications:** Twilio API (SMS / WhatsApp)
- **Frontend Dashboard:** React, Leaflet / MapLibre, Tailwind CSS
- **Orchestration:** Python Schedule Daemon

---

## 🚀 Quick Start & Local Setup

### 1. Prerequisites
- Python 3.11 or higher
- Git
- PostgreSQL 16 with PostGIS extension enabled

### 2. Clone the Repository
```bash
git clone https://github.com/aravchaudhary07-ai/AgniKavach.git
cd AgniKavach
```

### 3. Setup Python Virtual Environment
```powershell
# In Windows PowerShell:
python -m venv venv
.\venv\Scripts\activate

# Install dependencies:
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```env
# Database Settings
DATABASE_URL=postgresql://postgres:admin123@localhost:5432/agnikavach_db

# NASA FIRMS API
FIRMS_MAP_KEY=your_nasa_firms_map_key_here

# Twilio Alerts
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
EMERGENCY_ALERT_RECIPIENT=+91XXXXXXXXXX
```

---

## 🗺️ Roadmap & Phase Tracker

- [x] **Phase 1: Local Infrastructure Setup**
  - [ ] Task 1.1: Install PostgreSQL for Windows and enable PostGIS via Stack Builder.
  - [ ] Task 1.2: Design and create database schemas (`hotspots`, `land_cover`, `infrastructure`, `alerts_history`).
  - [x] Task 1.3: Set up Python virtual environment and install core geospatial/ML dependencies.
- [ ] **Phase 2: Data Scraping & Pipeline**
  - [ ] Task 2.1: Write Python scraper for NASA FIRMS API.
  - [ ] Task 2.2: Ingest OSM data (fire stations, roads) and WorldPop data.
  - [ ] Task 2.3: Ingest historical baseline heat signatures for industrial zones.
  - [ ] Task 2.4: Implement spatial cross-referencing (GeoPandas + Shapely) against Bhuvan boundaries.
- [ ] **Phase 3: AI Modeling & Risk Assessment**
  - [ ] Task 3.1: Feature Engineering (distance metrics, baseline heat comparisons).
  - [ ] Task 3.2: Train LightGBM classification model (Forest vs. Stubble vs. Industrial).
  - [ ] Task 3.3: Implement Fire Intensity & Capacity Analysis logic.
- [ ] **Phase 4: Automated Action & Routing**
  - [ ] Task 4.1: Integrate OSRM for emergency routing (single and multi-station routing).
  - [ ] Task 4.2: Build Twilio alert dispatcher (SMS & Email).
- [ ] **Phase 5: Interactive Web-GIS Dashboard**
  - [ ] Task 5.1: Build local FastAPI backend to serve database data.
  - [ ] Task 5.2: Build React + Leaflet frontend for interactive map visualization.
- [ ] **Phase 6: Pipeline Automation**
  - [ ] Task 6.1: Create a master Python scheduler script to link and run Phase 2, 3, and 4 automatically.

---

## 👥 Authors & Acknowledgments

- **Team AgniKavach** — Smart India Hackathon (SIH)
- **Data Providers:** NASA FIRMS, ISRO Bhuvan, OpenStreetMap Contributors, WorldPop Project
