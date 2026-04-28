/**
 * DisasterReady — Leaflet.js Map Module
 * Visualisasi peta risiko interaktif, posisi relawan, dan warga rentan.
 *
 * Sumber peta: © OpenStreetMap contributors (openstreetmap.org)
 * Library: Leaflet.js oleh Vladimir Agafonkin | leafletjs.com
 */

let map = null;
let riskLayers = {};
let volunteerMarkers = [];

const RISK_COLORS = {
  critical: { fill: '#ff2d55', opacity: 0.55, border: '#ff2d55' },
  high:     { fill: '#ff6b00', opacity: 0.45, border: '#ff6b00' },
  medium:   { fill: '#ffd60a', opacity: 0.35, border: '#ffd60a' },
  low:      { fill: '#30d158', opacity: 0.2,  border: '#30d158' },
  safe:     { fill: '#30d158', opacity: 0.08, border: '#30d158' },
};

// Koordinat tengah Bogor-Jabodetabek
const MAP_CENTER = [-6.580, 106.820];
const MAP_ZOOM = 10;

function initMap() {
  if (map) return;

  map = L.map('map', {
    center: MAP_CENTER,
    zoom: MAP_ZOOM,
    zoomControl: true,
    attributionControl: false,
  });

  // Tile layer dengan tema gelap
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 18,
    subdomains: 'abcd',
  }).addTo(map);

  // Labels layer (untuk nama kota)
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png', {
    maxZoom: 18,
    subdomains: 'abcd',
    opacity: 0.6,
  }).addTo(map);

  // Tambahkan marker kecamatan default
  addDefaultDistrictMarkers();
}

function addDefaultDistrictMarkers() {
  const districts = [
    { name: 'Bogor Tengah',  lat: -6.5954, lon: 106.7977 },
    { name: 'Bogor Selatan', lat: -6.6450, lon: 106.7920 },
    { name: 'Bogor Utara',   lat: -6.5623, lon: 106.7891 },
    { name: 'Cibinong',      lat: -6.4800, lon: 106.8537 },
    { name: 'Gunung Putri',  lat: -6.4560, lon: 106.9301 },
    { name: 'Ciawi',         lat: -6.6854, lon: 106.8712 },
    { name: 'Cisarua',       lat: -6.7060, lon: 106.9464 },
    { name: 'Ciomas',        lat: -6.6199, lon: 106.7638 },
    { name: 'Dramaga',       lat: -6.5545, lon: 106.7243 },
    { name: 'Depok',         lat: -6.4025, lon: 106.7942 },
  ];

  districts.forEach(d => {
    const icon = L.divIcon({
      className: '',
      html: `<div style="
        background: rgba(139,154,176,0.15);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 6px;
        padding: 3px 7px;
        font-family: Inter, sans-serif;
        font-size: 10px;
        color: rgba(255,255,255,0.5);
        white-space: nowrap;
      ">${d.name}</div>`,
      iconAnchor: [0, 0],
    });
    L.marker([d.lat, d.lon], { icon }).addTo(map);
  });
}

function updateRiskMap(geojsonData) {
  if (!map || !geojsonData) return;

  // Hapus layer lama
  Object.values(riskLayers).forEach(layer => map.removeLayer(layer));
  riskLayers = {};

  if (!geojsonData.features || geojsonData.features.length === 0) return;

  geojsonData.features.forEach(feature => {
    const props = feature.properties;
    const level = props.risk_level || 'safe';
    const style = RISK_COLORS[level] || RISK_COLORS.safe;

    const layer = L.geoJSON(feature, {
      style: {
        fillColor: style.fill,
        fillOpacity: style.opacity,
        color: style.border,
        weight: 2,
        opacity: 0.8,
      },
    });

    layer.bindPopup(`
      <div style="min-width: 200px; padding: 4px;">
        <div style="font-weight: 700; font-size: 13px; margin-bottom: 8px;">
          📍 ${props.district_name}
        </div>
        <div style="font-size: 11px; color: #8b9ab0; line-height: 1.8;">
          <div>Level: <strong style="color:${style.fill}">${level.toUpperCase()}</strong></div>
          <div>Skor Risiko: <strong>${(props.risk_score || 0).toFixed(2)}</strong></div>
          <div>Curah Hujan: <strong>${(props.rainfall_mm || 0).toFixed(0)} mm/hari</strong></div>
          <div>Warga Terdampak: <strong>${props.affected_residents || 0}</strong></div>
          <div>Kelompok Rentan: <strong style="color: #ffd60a">${props.vulnerable_residents || 0}</strong></div>
          <div>Confidence: <strong>${((props.confidence || 0) * 100).toFixed(0)}%</strong></div>
        </div>
        <div style="font-size: 9px; color: #4a5568; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;">
          ${(props.reasoning || '').substring(0, 100)}...
        </div>
      </div>
    `);

    layer.addTo(map);
    riskLayers[props.district_id] = layer;

    // Animasi pulse untuk zona kritis
    if (level === 'critical') {
      addPulseEffect(feature, style.fill);
    }
  });

  // Fit map ke bounds
  const group = L.featureGroup(Object.values(riskLayers));
  if (Object.keys(riskLayers).length > 0) {
    map.fitBounds(group.getBounds().pad(0.15));
  }
}

function addPulseEffect(feature, color) {
  // Tambahkan circle pulse di tengah polygon
  const coords = feature.geometry.coordinates[0];
  const centerLat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
  const centerLon = coords.reduce((s, c) => s + c[0], 0) / coords.length;

  L.circleMarker([centerLat, centerLon], {
    radius: 12,
    fillColor: color,
    fillOpacity: 0.6,
    color: color,
    weight: 2,
    className: 'pulse-marker',
  }).addTo(map);
}

function addVolunteerMarkers(assignments) {
  // Hapus marker lama
  volunteerMarkers.forEach(m => map.removeLayer(m));
  volunteerMarkers = [];

  if (!assignments || !assignments.length) return;

  assignments.forEach(a => {
    const icon = L.divIcon({
      className: '',
      html: `<div style="
        background: rgba(10,132,255,0.9);
        border: 2px solid #0a84ff;
        border-radius: 50%;
        width: 12px;
        height: 12px;
        box-shadow: 0 0 8px rgba(10,132,255,0.6);
      "></div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });

    if (!a.from_lat || !a.from_lon) return;

    const marker = L.marker([a.from_lat, a.from_lon], { icon });
    marker.bindPopup(`
      <div style="font-size: 11px; color: #8b9ab0; min-width: 160px;">
        <div style="font-weight: 700; color: #fff; font-size: 12px; margin-bottom: 6px;">
          🦺 ${a.volunteer_name}
        </div>
        <div>Organisasi: ${a.organization}</div>
        <div>Tujuan: ${a.to_district}</div>
        <div>ETA: ${(a.eta_minutes || 0).toFixed(0)} menit</div>
        <div>Jarak: ${(a.distance_km || 0).toFixed(1)} km</div>
        <div style="margin-top: 6px; color: #ffd60a;">Status: ${a.status}</div>
      </div>
    `);

    marker.addTo(map);
    volunteerMarkers.push(marker);
  });
}

// Init saat halaman dimuat
document.addEventListener('DOMContentLoaded', initMap);
