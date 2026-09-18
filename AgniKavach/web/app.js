/**
 * ==============================================================================
 * AGNI-KAVACH (SIH 26162) — TACTICAL WAR ROOM CONTROLLER
 * Cyber-Tactical Geospatial Command Center & Multi-Agency Dispatch Engine
 * ==============================================================================
 */

// Application State
const state = {
  incidents: [],
  infrastructure: [],
  baselines: [],
  alerts: [],
  selectedIncidentId: null,
  activeFilter: 'all',
  searchQuery: '',
  isSatelliteBasemap: false,
  soundEnabled: true,
  audioCtx: null,

  map: null,
  layers: {
    hotspots: null,
    firestations: null,
    hospitals: null,
    baselines: null,
    routes: null,
  },
  layerVisibility: {
    hotspots: true,
    firestations: true,
    hospitals: true,
    baselines: true,
  },
  basemapTiles: {
    dark: null,
    satellite: null,
  },
  markersMap: new Map(), // incidentId -> marker
  canvasAnimId: null,
};

// Tactical Color Tokens
const COLORS = {
  CRITICAL: '#ff334b',
  HIGH: '#ff7700',
  MODERATE: '#fbbf24',
  LOW: '#00f2fe',
  FIRE_TENDER: '#ff7700',
  AMBULANCE: '#00f2fe',
  SUCCESS: '#10b981',
};

const ICONS = {
  forest_fire: '🔥',
  crop_burn: '🌾',
  industrial_flare: '🏭',
  false_alarm: '⚪',
};

// ==============================================================================
// 1. INITIALIZATION & LIFECYCLE
// ==============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initAudio();
  initMap();
  bindUIEvents();
  loadAllTelemetry();

  // Periodic Telemetry Refresh (every 20s)
  setInterval(() => {
    refreshLiveTelemetry();
  }, 20000);
});

/**
 * Native Web Audio Synthesizer (No external audio files needed)
 */
function initAudio() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) {
      state.audioCtx = new AudioContext();
    }
  } catch (e) {
    console.warn('[AgniKavach Audio] Web Audio API unavailable:', e);
  }
}

function playTacticalBlip(freq = 880, duration = 0.08) {
  if (!state.soundEnabled || !state.audioCtx) return;
  try {
    if (state.audioCtx.state === 'suspended') {
      state.audioCtx.resume();
    }
    const osc = state.audioCtx.createOscillator();
    const gain = state.audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, state.audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(freq * 1.5, state.audioCtx.currentTime + duration);

    gain.gain.setValueAtTime(0.12, state.audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, state.audioCtx.currentTime + duration);

    osc.connect(gain);
    gain.connect(state.audioCtx.destination);
    osc.start();
    osc.stop(state.audioCtx.currentTime + duration);
  } catch (e) {}
}

function playDispatchSiren() {
  if (!state.soundEnabled || !state.audioCtx) return;
  try {
    if (state.audioCtx.state === 'suspended') {
      state.audioCtx.resume();
    }
    const osc = state.audioCtx.createOscillator();
    const gain = state.audioCtx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(440, state.audioCtx.currentTime);
    osc.frequency.linearRampToValueAtTime(880, state.audioCtx.currentTime + 0.25);
    osc.frequency.linearRampToValueAtTime(440, state.audioCtx.currentTime + 0.5);

    gain.gain.setValueAtTime(0.18, state.audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, state.audioCtx.currentTime + 0.55);

    osc.connect(gain);
    gain.connect(state.audioCtx.destination);
    osc.start();
    osc.stop(state.audioCtx.currentTime + 0.55);
  } catch (e) {}
}

// ==============================================================================
// 2. LEAFLET TACTICAL GIS MAP
// ==============================================================================
function initMap() {
  state.map = L.map('map', {
    center: [22.8, 81.5],
    zoom: 5,
    zoomControl: false,
  });

  L.control.zoom({ position: 'bottomright' }).addTo(state.map);

  // Basemaps: CartoDB Dark Matter & Esri Satellite
  state.basemapTiles.dark = L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    {
      attribution: '&copy; CARTO &bull; AgniKavach',
      maxZoom: 19,
      subdomains: 'abcd',
    }
  ).addTo(state.map);

  state.basemapTiles.satellite = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {
      attribution: '&copy; Esri, Maxar &bull; AgniKavach',
      maxZoom: 18,
    }
  );

  // Layer Groups
  state.layers.baselines = L.layerGroup().addTo(state.map);
  state.layers.firestations = L.layerGroup().addTo(state.map);
  state.layers.hospitals = L.layerGroup().addTo(state.map);
  state.layers.routes = L.layerGroup().addTo(state.map);
  state.layers.hotspots = L.layerGroup().addTo(state.map);

  // Crosshairs Coordinate Tracker
  state.map.on('mousemove', (e) => {
    const coordsEl = document.getElementById('hud-center-coords');
    if (coordsEl) {
      coordsEl.textContent = `${e.latlng.lat.toFixed(4)}° N, ${e.latlng.lng.toFixed(4)}° E`;
    }
  });

  state.map.on('click', (e) => {
    // If click was on empty map, don't clear unless desired
  });
}

// ==============================================================================
// 3. EVENT LISTENERS & OPERATOR CONTROLS
// ==============================================================================
function bindUIEvents() {
  // Basemap Switcher
  const btnToggleBasemap = document.getElementById('btn-toggle-basemap');
  const basemapLabel = document.getElementById('basemap-label');
  if (btnToggleBasemap) {
    btnToggleBasemap.addEventListener('click', () => {
      playTacticalBlip(1040);
      state.isSatelliteBasemap = !state.isSatelliteBasemap;
      if (state.isSatelliteBasemap) {
        state.map.removeLayer(state.basemapTiles.dark);
        state.basemapTiles.satellite.addTo(state.map);
        basemapLabel.textContent = 'Dark Grid';
        showToast('BASEMAP CHANGED', 'Switched to High-Resolution Optical Satellite View', 'info');
      } else {
        state.map.removeLayer(state.basemapTiles.satellite);
        state.basemapTiles.dark.addTo(state.map);
        basemapLabel.textContent = 'Satellite Imagery';
        showToast('BASEMAP CHANGED', 'Switched to Tactical Dark Matter GIS View', 'info');
      }
    });
  }

  // Audio Toggle
  const btnToggleSound = document.getElementById('btn-toggle-sound');
  const soundIcon = document.getElementById('sound-icon');
  if (btnToggleSound) {
    btnToggleSound.addEventListener('click', () => {
      state.soundEnabled = !state.soundEnabled;
      soundIcon.textContent = state.soundEnabled ? '🔊' : '🔇';
      if (state.soundEnabled) playTacticalBlip(1200);
    });
  }

  // Layer Visibility Toggles
  const bindLayerToggle = (btnId, layerKey, label) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener('click', () => {
      playTacticalBlip(780);
      state.layerVisibility[layerKey] = !state.layerVisibility[layerKey];
      btn.classList.toggle('active', state.layerVisibility[layerKey]);
      const layer = state.layers[layerKey];
      if (layer) {
        if (state.layerVisibility[layerKey]) {
          state.map.addLayer(layer);
        } else {
          state.map.removeLayer(layer);
        }
      }
    });
  };

  bindLayerToggle('layer-toggle-hotspots', 'hotspots', 'Hotspots');
  bindLayerToggle('layer-toggle-firestations', 'firestations', 'Fire Stations');
  bindLayerToggle('layer-toggle-hospitals', 'hospitals', 'Trauma Centers');
  bindLayerToggle('layer-toggle-baselines', 'baselines', 'Baselines');

  // Trigger Satellite Pipeline Scan
  const btnTrigger = document.getElementById('btn-trigger-pipeline');
  if (btnTrigger) {
    btnTrigger.addEventListener('click', runSatellitePipeline);
  }

  // Search Input
  const searchInput = document.getElementById('input-incident-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.toLowerCase().trim();
      renderIncidentStream();
      renderHotspotMarkers();
    });
  }

  // Filter Chips Matrix
  const chips = document.querySelectorAll('.filter-chip');
  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      playTacticalBlip(920);
      chips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      state.activeFilter = chip.getAttribute('data-filter');
      renderIncidentStream();
      renderHotspotMarkers();
    });
  });

  // Dock Close Button
  const btnCloseDock = document.getElementById('btn-close-dock');
  if (btnCloseDock) {
    btnCloseDock.addEventListener('click', () => {
      playTacticalBlip(600);
      closeRouteDock();
    });
  }

  // Dock Dispatch Action Button
  const btnDockDispatch = document.getElementById('btn-dock-dispatch-action');
  if (btnDockDispatch) {
    btnDockDispatch.addEventListener('click', () => {
      if (state.selectedIncidentId) {
        dispatchEmergencyAlert(state.selectedIncidentId);
      }
    });
  }
}

// ==============================================================================
// 4. DATA TELEMETRY INGESTION
// ==============================================================================
async function loadAllTelemetry() {
  try {
    await Promise.all([
      fetchIncidents(),
      fetchInfrastructure(),
      fetchBaselines(),
      fetchAlertsHistory(),
    ]);

    renderTickerMetrics();
    renderBaselines();
    renderInfrastructure();
    renderHotspotMarkers();
    renderIncidentStream();

    // Auto-select first critical incident for immediate tactical inspection
    const critical = state.incidents.find((i) => i.severity_tier === 'CRITICAL');
    if (critical) {
      selectIncident(critical.id, true);
    } else if (state.incidents.length > 0) {
      selectIncident(state.incidents[0].id, true);
    }
  } catch (err) {
    console.error('[AgniKavach] Telemetry Load Error:', err);
    showToast('TELEMETRY ERROR', err.message, 'critical');
  }
}

async function refreshLiveTelemetry() {
  try {
    await Promise.all([fetchIncidents(), fetchAlertsHistory()]);
    renderTickerMetrics();
    renderHotspotMarkers();
    renderIncidentStream();
  } catch (err) {
    console.warn('[AgniKavach] Background Poll Warning:', err);
  }
}

async function fetchIncidents() {
  const res = await fetch('/api/incidents');
  if (!res.ok) throw new Error(`Incidents HTTP ${res.status}`);
  const data = await res.json();
  state.incidents = data.incidents || [];
}

async function fetchInfrastructure() {
  const res = await fetch('/api/infrastructure');
  if (!res.ok) throw new Error(`Infrastructure HTTP ${res.status}`);
  state.infrastructure = await res.json();
}

async function fetchBaselines() {
  const res = await fetch('/api/baselines');
  if (!res.ok) throw new Error(`Baselines HTTP ${res.status}`);
  state.baselines = await res.json();
}

async function fetchAlertsHistory() {
  const res = await fetch('/api/alerts?limit=50');
  if (!res.ok) throw new Error(`Alerts HTTP ${res.status}`);
  state.alerts = await res.json();
  renderAlertsHistory();
}

/**
 * Operator Action: Run Satellite & AI Pipeline
 */
async function runSatellitePipeline() {
  playTacticalBlip(1100);
  const btn = document.getElementById('btn-trigger-pipeline');
  const originalHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span>SCANNING SATELLITES...</span>';
  showToast('PIPELINE TRIGGERED', 'Ingesting NASA FIRMS & running LightGBM classifier...', 'info');

  try {
    const res = await fetch('/api/pipeline/run', { method: 'POST' });
    const data = await res.json();
    playTacticalBlip(1320);
    showToast(
      'SCAN COMPLETE',
      `Processed ${data.scored_incidents_count || 0} incidents. PostGIS records updated.`,
      'success'
    );
    await loadAllTelemetry();
  } catch (err) {
    showToast('SCAN FAILED', err.message, 'critical');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }
}

// ==============================================================================
// 5. TICKER METRICS & COUNTERS
// ==============================================================================
function renderTickerMetrics() {
  const total = state.incidents.length;
  const critical = state.incidents.filter((i) => i.severity_tier === 'CRITICAL').length;
  const crop = state.incidents.filter((i) => i.fire_type === 'crop_burn').length;
  const ind = state.incidents.filter((i) => i.fire_type === 'industrial_flare').length;
  const forest = state.incidents.filter((i) => i.fire_type === 'forest_fire').length;

  document.getElementById('stat-total-hotspots').textContent = total;
  document.getElementById('stat-critical-fires').textContent = critical;
  document.getElementById('stat-crop-burns').textContent = crop;
  document.getElementById('stat-industrial-flares').textContent = ind;
  document.getElementById('stat-dispatched-alerts').textContent = state.alerts.length;

  // Queue Counts
  document.getElementById('active-queue-count').textContent = `${total} ACTIVE`;
  document.getElementById('count-all').textContent = total;
  document.getElementById('count-crit').textContent = critical;
  document.getElementById('count-forest').textContent = forest;
  document.getElementById('count-crop').textContent = crop;
  document.getElementById('count-ind').textContent = ind;

  // Threat State
  const threatEl = document.getElementById('hud-threat-state');
  if (threatEl) {
    if (critical > 0) {
      threatEl.textContent = `DEFCON 1 &bull; ${critical} CRITICAL WILDFIRES ACTIVE`;
      threatEl.className = 'hud-val text-critical';
    } else {
      threatEl.textContent = 'DEFCON 3 &bull; NOMINAL REGIONAL SURVEILLANCE';
      threatEl.className = 'hud-val text-green';
    }
  }
}

// ==============================================================================
// 6. MAP LAYERS RENDERING
// ==============================================================================

/**
 * Render Industrial Baselines & Buffer Rings
 */
function renderBaselines() {
  state.layers.baselines.clearLayers();

  state.baselines.forEach((b) => {
    const radius = b.buffer_radius_m || 3000;
    const circle = L.circle([b.latitude, b.longitude], {
      radius: radius,
      color: '#00f2fe',
      weight: 1.2,
      opacity: 0.6,
      fillColor: '#00f2fe',
      fillOpacity: 0.05,
      dashArray: '4, 8',
    });

    circle.bindTooltip(
      `<b>🏭 ${b.name}</b><br><span style="font-size:10px;color:#94a3b8">Baseline Buffer: ${(radius / 1000).toFixed(1)} km &bull; Thresh: ${b.typical_frp_threshold} MW</span>`,
      { sticky: true }
    );

    state.layers.baselines.addLayer(circle);
  });
}

/**
 * Render Emergency Responders (Fire Stations & Trauma Hospitals)
 */
function renderInfrastructure() {
  state.layers.firestations.clearLayers();
  state.layers.hospitals.clearLayers();

  state.infrastructure.forEach((item) => {
    const isFire = item.type === 'fire_station';
    const iconChar = isFire ? '🚒' : '🏥';
    const pinClass = isFire ? 'pin-fire' : 'pin-hosp';

    const customIcon = L.divIcon({
      className: 'infra-marker-wrapper',
      html: `<div class="facility-marker-pin ${pinClass}">${iconChar}</div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });

    const marker = L.marker([item.latitude, item.longitude], { icon: customIcon });

    marker.bindPopup(`
      <div style="font-family:'Inter',sans-serif;color:#fff;background:#090e1c;padding:12px;border-radius:8px;font-size:12px;min-width:210px;border:1px solid rgba(255,255,255,0.1);">
        <h4 style="margin:0 0 6px;color:${isFire ? '#ff7700' : '#00f2fe'};display:flex;align-items:center;gap:6px;">
          <span>${iconChar}</span> ${item.name}
        </h4>
        <div style="color:#94a3b8;margin-bottom:4px;"><b>Type:</b> ${isFire ? 'Fire Brigade Station' : 'Trauma & Burn Center'}</div>
        <div style="color:#94a3b8;margin-bottom:4px;"><b>Capacity:</b> ${item.capacity || 'Ready Unit'}</div>
        <div style="color:#34d399;font-family:'JetBrains Mono',monospace;"><b>Direct Line:</b> ${item.contact_phone || 'Emergency Desk'}</div>
        <div style="color:#64748b;font-size:10px;margin-top:6px;">${item.address || ''}</div>
      </div>
    `);

    if (isFire) {
      state.layers.firestations.addLayer(marker);
    } else {
      state.layers.hospitals.addLayer(marker);
    }
  });
}

/**
 * Render Pulsing Radar Thermal Markers on Map
 */
function renderHotspotMarkers() {
  state.layers.hotspots.clearLayers();
  state.markersMap.clear();

  const filtered = getFilteredIncidents();

  filtered.forEach((h) => {
    const tier = h.severity_tier || 'LOW';
    const ringClass = `ring-${tier.substring(0, 4).toLowerCase()}`;
    const color = COLORS[tier] || COLORS.LOW;
    const icon = ICONS[h.fire_type] || '🔥';

    const divIcon = L.divIcon({
      className: 'tactical-marker-container',
      html: `
        <div class="tactical-marker-box" id="map-marker-${h.id}">
          <span class="marker-shockwave-ring ${ringClass}"></span>
          <div class="marker-core-glow" style="background:${color};">${icon}</div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });

    const marker = L.marker([h.latitude, h.longitude], { icon: divIcon });

    marker.bindPopup(`
      <div style="font-family:'Inter',sans-serif;color:#f8fafc;background:#090e1c;padding:12px;border-radius:8px;font-size:12px;min-width:240px;border:1px solid rgba(255,255,255,0.12);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <b style="font-size:14px;color:${color}">${icon} Incident #${h.id}</b>
          <span class="mini-tier-badge tier-${tier.substring(0, 4).toLowerCase()}-badge">${tier}</span>
        </div>
        <div style="margin-bottom:6px;color:#94a3b8;">
          Type: <b style="color:#fff;">${h.fire_type?.replace('_', ' ').toUpperCase()}</b>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;background:rgba(0,0,0,0.35);padding:6px 8px;border-radius:4px;margin-bottom:8px;font-family:'JetBrains Mono',monospace;font-size:10px;">
          <div><span style="color:#64748b">FRP:</span> <b>${h.frp} MW</b></div>
          <div><span style="color:#64748b">SCORE:</span> <b style="color:${color}">${h.risk_score}/100</b></div>
        </div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">
          🚒 <b>Fire:</b> ${h.nearest_fire_station?.name || 'Nearest'} (${h.nearest_fire_station?.distance_km} km)
        </div>
        <div style="font-size:11px;color:#00f2fe;margin-bottom:10px;">
          🏥 <b>Trauma:</b> ${h.nearest_hospital?.name || 'Nearest'} (${h.nearest_hospital?.distance_km} km)
        </div>
        <button onclick="window.AgniWarRoom.inspectIncident(${h.id})" style="width:100%;background:linear-gradient(135deg, #ef4444, #ff7700);border:none;color:#fff;padding:6px;border-radius:4px;font-weight:700;font-size:10px;font-family:'Orbitron',sans-serif;cursor:pointer;">
          TACTICAL DOSSIER & ROUTES
        </button>
      </div>
    `);

    marker.on('click', () => {
      selectIncident(h.id, false);
    });

    state.markersMap.set(h.id, marker);
    state.layers.hotspots.addLayer(marker);
  });
}

// ==============================================================================
// 7. LEFT PANEL: ANOMALY RADAR STREAM
// ==============================================================================
function getFilteredIncidents() {
  return state.incidents.filter((i) => {
    // Tab filter
    if (state.activeFilter === 'critical' && i.severity_tier !== 'CRITICAL') return false;
    if (
      state.activeFilter !== 'all' &&
      state.activeFilter !== 'critical' &&
      i.fire_type !== state.activeFilter
    )
      return false;

    // Search query filter
    if (state.searchQuery) {
      const q = state.searchQuery;
      const idMatch = String(i.id).includes(q);
      const typeMatch = i.fire_type?.toLowerCase().includes(q);
      const fireMatch = i.nearest_fire_station?.name?.toLowerCase().includes(q);
      const hospMatch = i.nearest_hospital?.name?.toLowerCase().includes(q);
      if (!idMatch && !typeMatch && !fireMatch && !hospMatch) return false;
    }

    return true;
  });
}

function renderIncidentStream() {
  const container = document.getElementById('incident-cards-container');
  const filtered = getFilteredIncidents();

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;color:#64748b;padding:40px 10px;font-family:var(--font-mono);font-size:11px;">
        NO ANOMALIES MATCHING QUERY
      </div>
    `;
    return;
  }

  container.innerHTML = filtered
    .map((h) => {
      const tier = h.severity_tier || 'LOW';
      const color = COLORS[tier] || COLORS.LOW;
      const icon = ICONS[h.fire_type] || '🔥';
      const isSelected = state.selectedIncidentId === h.id ? 'selected' : '';
      const score = (h.risk_score || 0).toFixed(1);

      return `
        <div class="mini-incident-card ${isSelected}" id="mini-card-${h.id}" onclick="window.AgniWarRoom.inspectIncident(${h.id})" style="--card-accent:${color};">
          <div class="mini-card-head">
            <div class="mini-card-title" style="color:${color};">
              <span>${icon}</span>
              <span>INCIDENT #${h.id}</span>
            </div>
            <span class="mini-tier-badge tier-${tier.substring(0, 4).toLowerCase()}-badge">${tier}</span>
          </div>
          <div class="mini-card-metrics">
            <span>FRP: <b>${h.frp} MW</b></span>
            <span>THREAT: <b style="color:${color};">${score}</b></span>
            <span>TEMP: <b>${h.brightness ? h.brightness.toFixed(0) : '--'} K</b></span>
          </div>
        </div>
      `;
    })
    .join('');
}

// ==============================================================================
// 8. INCIDENT INSPECTION, DOSSIER & OPTICAL CANVAS
// ==============================================================================
async function selectIncident(incidentId, flyTo = true) {
  playTacticalBlip(880);
  state.selectedIncidentId = incidentId;

  // Highlight in Left Queue
  document.querySelectorAll('.mini-incident-card').forEach((c) => c.classList.remove('selected'));
  const activeMini = document.getElementById(`mini-card-${incidentId}`);
  if (activeMini) {
    activeMini.classList.add('selected');
    activeMini.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  const incident = state.incidents.find((i) => i.id === incidentId);
  if (!incident) return;

  if (flyTo) {
    state.map.flyTo([incident.latitude, incident.longitude], 10, { duration: 1.2 });
    const marker = state.markersMap.get(incidentId);
    if (marker) marker.openPopup();
  }

  // Populate Right Dossier
  renderDossier(incident);

  // Animate Sentinel-2 Optical Canvas
  renderOpticalCanvas(incident);

  // Load and Plot Dual Turn-by-Turn Routes on Map & Open Floating Bottom Dock
  await plotDualRoutes(incident);
}

/**
 * Render Detailed Dossier in Right Panel
 */
function renderDossier(incident) {
  document.getElementById('dossier-empty-state').style.display = 'none';
  const details = document.getElementById('dossier-details-view');
  details.style.display = 'flex';

  const tier = incident.severity_tier || 'LOW';
  const color = COLORS[tier] || COLORS.LOW;

  // Identity
  document.getElementById('dossier-incident-id').textContent = `INCIDENT #${incident.id} &bull; ${incident.fire_type?.replace('_', ' ').toUpperCase()}`;
  document.getElementById('dossier-sensor-tag').textContent = `${incident.satellite || 'VIIRS'} / ${incident.instrument || 'NRT'}`;
  document.getElementById('dossier-coords').textContent = `${incident.latitude.toFixed(4)}° N, ${incident.longitude.toFixed(4)}° E`;
  document.getElementById('dossier-timestamp').textContent = `Acquired: ${incident.acq_date || 'Today'} ${incident.acq_time || ''} UTC`;

  // Tier Badge
  const tierBadge = document.getElementById('dossier-tier-badge');
  tierBadge.textContent = tier;
  tierBadge.className = `badge-dossier-tier mini-tier-badge tier-${tier.substring(0, 4).toLowerCase()}-badge`;

  // Threat Index Gauge
  const score = Math.min(Math.max(incident.risk_score || 0, 0), 100);
  document.getElementById('dossier-threat-score').textContent = `${score.toFixed(1)} / 100`;
  document.getElementById('dossier-gauge-fill').style.width = `${score}%`;

  // Physical Telemetry
  document.getElementById('dossier-frp').textContent = `${incident.frp} MW`;
  document.getElementById('dossier-brightness').textContent = `${incident.brightness?.toFixed(1) || '--'} K`;
  document.getElementById('dossier-landcover').textContent = incident.fire_type === 'crop_burn' ? 'Agricultural Fields' : incident.fire_type === 'forest_fire' ? 'Dense Deciduous Forest' : 'Industrial Complex';
  document.getElementById('dossier-industrial-status').textContent = incident.fire_type === 'industrial_flare' ? 'Active Heat Baseline' : 'Zero Baseline Suppressed';

  // Responders
  document.getElementById('dossier-fire-name').textContent = incident.nearest_fire_station?.name || 'Nearest Station';
  document.getElementById('dossier-fire-dist').textContent = `${incident.nearest_fire_station?.distance_km ?? '--'} km`;
  document.getElementById('dossier-fire-phone').textContent = incident.nearest_fire_station?.contact_phone || 'Emergency Direct';

  document.getElementById('dossier-hospital-name').textContent = incident.nearest_hospital?.name || 'Nearest Trauma Center';
  document.getElementById('dossier-hospital-dist').textContent = `${incident.nearest_hospital?.distance_km ?? '--'} km`;
  document.getElementById('dossier-hospital-phone').textContent = incident.nearest_hospital?.contact_phone || 'Emergency Direct';
}

/**
 * Sentinel-2 Multi-Spectral Optical Canvas Simulation
 */
function renderOpticalCanvas(incident) {
  const canvas = document.getElementById('optical-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  if (state.canvasAnimId) {
    cancelAnimationFrame(state.canvasAnimId);
  }

  const isCritical = incident.severity_tier === 'CRITICAL';
  const isForest = incident.fire_type === 'forest_fire';
  const isCrop = incident.fire_type === 'crop_burn';

  // Metrics update
  const probEl = document.getElementById('dossier-fire-prob');
  const swirEl = document.getElementById('dossier-swir-val');
  const nbrEl = document.getElementById('dossier-nbr-val');
  const cnnVerdictEl = document.getElementById('dossier-cnn-verdict');

  if (isForest) {
    probEl.textContent = '99.4%';
    swirEl.textContent = '0.842';
    nbrEl.textContent = '0.615';
    cnnVerdictEl.textContent = 'CONFIRMED ACTIVE FLAME';
    cnnVerdictEl.className = 'cnn-badge cnn-confirmed';
  } else if (isCrop) {
    probEl.textContent = '91.8%';
    swirEl.textContent = '0.450';
    nbrEl.textContent = '0.380';
    cnnVerdictEl.textContent = 'CROP STUBBLE BURN';
    cnnVerdictEl.className = 'cnn-badge text-amber';
  } else {
    probEl.textContent = '12.1%';
    swirEl.textContent = '0.120';
    nbrEl.textContent = '0.040';
    cnnVerdictEl.textContent = 'SUPPRESSED BASELINE';
    cnnVerdictEl.className = 'cnn-badge text-cyan';
  }

  let frame = 0;
  function draw() {
    frame++;
    ctx.clearRect(0, 0, w, h);

    // 1. Base terrain simulation (Optical RGB)
    const grad = ctx.createLinearGradient(0, 0, w, h);
    if (isForest) {
      grad.addColorStop(0, '#0a2312');
      grad.addColorStop(1, '#051409');
    } else if (isCrop) {
      grad.addColorStop(0, '#241a08');
      grad.addColorStop(1, '#140e04');
    } else {
      grad.addColorStop(0, '#101520');
      grad.addColorStop(1, '#080c14');
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // 2. Texture noise
    ctx.fillStyle = 'rgba(255, 255, 255, 0.03)';
    for (let i = 0; i < 80; i++) {
      const rx = (Math.sin(i * 99 + frame * 0.01) * 0.5 + 0.5) * w;
      const ry = (Math.cos(i * 33 + frame * 0.01) * 0.5 + 0.5) * h;
      ctx.fillRect(rx, ry, 2, 2);
    }

    if (isForest || isCrop) {
      // 3. SWIR Band 12 Thermal Bloom
      const cx = w / 2;
      const cy = h / 2;
      const pulse = Math.sin(frame * 0.08) * 6;
      const r = (isForest ? 40 : 25) + pulse;

      const swirGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, r);
      swirGrad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
      swirGrad.addColorStop(0.2, 'rgba(255, 100, 0, 0.85)');
      swirGrad.addColorStop(0.6, 'rgba(255, 20, 40, 0.45)');
      swirGrad.addColorStop(1, 'rgba(255, 0, 0, 0)');

      ctx.fillStyle = swirGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();

      // 4. Optical Smoke Plume (Wind drift towards upper right)
      ctx.fillStyle = 'rgba(200, 210, 220, 0.15)';
      ctx.beginPath();
      ctx.ellipse(
        cx + 30 + Math.sin(frame * 0.05) * 8,
        cy - 20,
        50 + pulse,
        25,
        -Math.PI / 6,
        0,
        Math.PI * 2
      );
      ctx.fill();
    }

    // 5. Tactical CRT Scanline overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
    for (let y = 0; y < h; y += 4) {
      ctx.fillRect(0, y, w, 1);
    }

    state.canvasAnimId = requestAnimationFrame(draw);
  }

  draw();
}

// ==============================================================================
// 9. DUAL ROUTE GENERATION & FLOATING DOCK
// ==============================================================================
async function plotDualRoutes(incident) {
  state.layers.routes.clearLayers();

  try {
    const res = await fetch(`/api/routes/${incident.id}`);
    if (!res.ok) {
      console.warn(`[AgniKavach] No routes computed for Incident #${incident.id}`);
      return;
    }

    const data = await res.json();
    const fb = data.fire_brigade_route;
    const med = data.medical_ambulance_route;

    const latlngsForBounds = [];

    // 1. Fire Brigade Route (Neon Orange)
    if (fb && fb.route_geojson && fb.route_geojson.coordinates) {
      const latlngs = fb.route_geojson.coordinates.map((c) => [c[1], c[0]]);
      latlngsForBounds.push(...latlngs);

      // Glow Underlay
      const glow = L.polyline(latlngs, {
        color: COLORS.FIRE_TENDER,
        weight: 9,
        opacity: 0.35,
        lineCap: 'round',
      });

      // Sharp Core
      const core = L.polyline(latlngs, {
        color: COLORS.FIRE_TENDER,
        weight: 4,
        opacity: 0.95,
        lineCap: 'round',
      });

      core.bindTooltip(
        `<b>🚒 Fire Tender Route:</b> ${fb.station_name}<br>Dist: ${fb.distance_km} km &bull; ETA: ${fb.duration_minutes} mins`,
        { sticky: true }
      );

      state.layers.routes.addLayer(glow);
      state.layers.routes.addLayer(core);
    }

    // 2. Medical Evacuation Route (Neon Cyan Dashed)
    if (med && med.route_geojson && med.route_geojson.coordinates) {
      const latlngs = med.route_geojson.coordinates.map((c) => [c[1], c[0]]);
      latlngsForBounds.push(...latlngs);

      // Glow Underlay
      const glow = L.polyline(latlngs, {
        color: COLORS.AMBULANCE,
        weight: 9,
        opacity: 0.35,
        lineCap: 'round',
      });

      // Dashed Core
      const core = L.polyline(latlngs, {
        color: COLORS.AMBULANCE,
        weight: 4,
        opacity: 0.95,
        dashArray: '8, 8',
        lineCap: 'round',
      });

      core.bindTooltip(
        `<b>🏥 Medical Ambulance Route:</b> ${med.hospital_name}<br>Dist: ${med.distance_km} km &bull; ETA: ${med.duration_minutes} mins`,
        { sticky: true }
      );

      state.layers.routes.addLayer(glow);
      state.layers.routes.addLayer(core);
    }

    // Fit map bounds to view both routes
    if (latlngsForBounds.length > 0) {
      const bounds = L.latLngBounds(latlngsForBounds);
      state.map.fitBounds(bounds, { padding: [60, 60], maxZoom: 12 });
    }

    // Open Floating Bottom Dock with Telemetry
    openRouteDock(incident, fb, med);
  } catch (err) {
    console.error('[AgniKavach] Route plot error:', err);
  }
}

function openRouteDock(incident, fb, med) {
  const dock = document.getElementById('route-dispatch-dock');
  document.getElementById('dock-incident-id').textContent = incident.id;

  // Fire Brigade Card
  if (fb) {
    document.getElementById('dock-fire-station-name').textContent = fb.station_name;
    document.getElementById('dock-fire-distance').textContent = `${fb.distance_km} km`;
    document.getElementById('dock-fire-eta').textContent = `${fb.duration_minutes} mins`;
    document.getElementById('dock-fire-phone').textContent = fb.contact_phone || 'Emergency Control';
  }

  // Hospital Card
  if (med) {
    document.getElementById('dock-hospital-name').textContent = med.hospital_name;
    document.getElementById('dock-hospital-distance').textContent = `${med.distance_km} km`;
    document.getElementById('dock-hospital-eta').textContent = `${med.duration_minutes} mins`;
    document.getElementById('dock-hospital-phone').textContent = med.contact_phone || 'Emergency Control';
  }

  dock.classList.add('dock-open');
}

function closeRouteDock() {
  const dock = document.getElementById('route-dispatch-dock');
  dock.classList.remove('dock-open');
}

// ==============================================================================
// 10. MULTI-AGENCY EMERGENCY ALERT DISPATCH
// ==============================================================================
async function dispatchEmergencyAlert(incidentId) {
  playDispatchSiren();

  const btn = document.getElementById('btn-dock-dispatch-action');
  const originalHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span>TRANSMITTING EMERGENCY SMS...</span>';

  showToast('TRANSMITTING ALERTS', `Broadcasting turn-by-turn SMS for Incident #${incidentId}...`, 'info');

  try {
    const res = await fetch(`/api/dispatch/${incidentId}`, { method: 'POST' });
    if (!res.ok) throw new Error(`Dispatch HTTP ${res.status}`);
    const data = await res.json();

    playTacticalBlip(1400);
    showToast(
      'ALERTS DISPATCHED',
      `Audited ${data.dispatched_alerts?.length || 0} transmissions to Fire Brigade & Trauma Units!`,
      'success'
    );
    await fetchAlertsHistory();
    renderTickerMetrics();
  } catch (err) {
    showToast('DISPATCH FAILED', err.message, 'critical');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }
}

// ==============================================================================
// 11. AUDIT HISTORY DRAWER
// ==============================================================================
function renderAlertsHistory() {
  const container = document.getElementById('alerts-history-container');
  const badge = document.getElementById('badge-alert-count');
  if (badge) badge.textContent = `${state.alerts.length} Dispatched`;

  if (state.alerts.length === 0) {
    container.innerHTML = '<div class="no-alerts-hint">No emergency transmissions logged yet.</div>';
    return;
  }

  container.innerHTML = state.alerts
    .slice(0, 10)
    .map((a) => {
      const isMed = a.alert_type?.includes('HOSPITAL');
      const typeLabel = isMed ? '🏥 MEDICAL TRAUMA SMS' : '🚒 FIRE BRIGADE SMS';
      const timeStr = a.dispatched_at ? new Date(a.dispatched_at).toLocaleTimeString() : 'Just now';

      return `
        <div class="audit-entry ${isMed ? 'audit-med' : ''}">
          <div class="audit-head">
            <span style="color:${isMed ? '#00f2fe' : '#ff334b'};">${typeLabel} (#${a.hotspot_id})</span>
            <span style="color:#64748b;">${timeStr}</span>
          </div>
          <div class="audit-msg">
            <b>To:</b> ${a.recipient_contact} &bull; <b>Dist:</b> ${a.distance_km || '--'} km &bull; <b>ETA:</b> ${a.eta_minutes || '--'}m
          </div>
        </div>
      `;
    })
    .join('');
}

// ==============================================================================
// 12. TOAST NOTIFICATION SYSTEM
// ==============================================================================
function showToast(title, message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-title" style="color:${type === 'critical' ? '#ff334b' : type === 'success' ? '#10b981' : '#00f2fe'};">
      ${title}
    </div>
    <div class="toast-msg">${message}</div>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Global API Hook
window.AgniWarRoom = {
  inspectIncident: (id) => selectIncident(id, true),
  dispatchEmergencyAlert,
};
