/**
 * DisasterReady — Main Dashboard Controller
 * Real-time dashboard via Server-Sent Events (SSE).
 * Mengelola views, update metrik, audit log, dan simulasi.
 */

const API_BASE = window.location.origin;
let sseSource = null;
let currentDisasterId = null;
let simStartTime = null;
let pipelineTimer = null;
let lastRiskMapTimestamp = null;
let lastAuditLatestId = null;
let lastAlertLatestId = null;
let lastAssignmentTimestamp = null;

// ── View Navigation ────────────────────────────────────────────────────────────
function showView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const view = document.getElementById(`view-${viewName}`);
  const navBtn = document.getElementById(`nav-${viewName}`);

  if (view) view.classList.add('active');
  if (navBtn) navBtn.classList.add('active');

  const titles = {
    dashboard: ['Dashboard Real-Time', 'Monitoring BMKG & Koordinasi Respons Bencana'],
    agents: ['Status Agen', 'Monitor 6 agen yang bekerja secara kolaboratif'],
    alerts: ['Alert History', 'Log peringatan dini yang telah dikirim'],
    audit: ['Audit Log', 'Transparansi penuh — semua aksi agen tercatat'],
    simulation: ['Panel Simulasi Demo', 'Jalankan skenario banjir Jabodetabek'],
  };

  const [title, sub] = titles[viewName] || ['Dashboard', ''];
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-sub').textContent = sub;

  if (viewName === 'dashboard' && map) {
    setTimeout(() => map.invalidateSize(), 100);
  }
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('id-ID', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  document.getElementById('time-display').textContent = timeStr + ' WIB';
}
setInterval(updateClock, 1000);
updateClock();

// ── SSE Real-time Updates ──────────────────────────────────────────────────────
function startSSE() {
  if (sseSource) sseSource.close();

  sseSource = new EventSource(`${API_BASE}/api/stream`);
  sseSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      updateDashboard(data);
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  };
  sseSource.onerror = () => {
    // Retry silently
  };
}

function updateDashboard(data) {
  const disasters = data.disasters || [];
  const alerts = data.alerts || [];
  const auditLog = data.audit_log || [];
  const reports = data.reports || [];
  const systemState = data.system_state || {};
  const riskMaps = data.risk_maps || [];
  const assignments = data.assignments || [];

  // ── Restore currentDisasterId setelah page refresh ──────────────────────
  // currentDisasterId adalah variabel JS yang hilang saat refresh.
  // Coba pulihkan dari: (1) bencana aktif, atau (2) last_disaster_id di state.
  if (!currentDisasterId) {
    const activeDisaster = disasters.find(d => d.status === 'active');
    if (activeDisaster) {
      currentDisasterId = activeDisaster.id;
    } else if (systemState.last_disaster_id &&
               (riskMaps.length > 0 || assignments.length > 0)) {
      currentDisasterId = systemState.last_disaster_id;
    }
  }

  // Guard: jika benar-benar tidak ada data, cukup update metrik
  if (!currentDisasterId) {
    updateMetrics(disasters, alerts, systemState);
    return;
  }

  // Metrik
  updateMetrics(disasters, alerts, systemState);

  // Peta risiko
  const latestMap = riskMaps[riskMaps.length - 1];
  if (latestMap?.geojson && latestMap.generated_at !== lastRiskMapTimestamp) {
    updateRiskMap(latestMap.geojson);
    lastRiskMapTimestamp = latestMap.generated_at;
  }

  // Relawan di peta — hanya update jika assignment adalah untuk bencana SAAT INI
  // Gunakan composite key (dispatched_at + status) agar re-render terjadi
  // saat koordinator mengkonfirmasi (status berubah pending_confirmation → confirmed)
  const latestAssignment = assignments[assignments.length - 1];
  if (latestAssignment && latestAssignment.disaster_id === currentDisasterId) {
    const assignmentKey = `${latestAssignment.dispatched_at}-${latestAssignment.status}`;
    if (assignmentKey !== lastAssignmentTimestamp) {
      addVolunteerMarkers(latestAssignment.assignments || []);
      lastAssignmentTimestamp = assignmentKey;
    }
  } else if (!latestAssignment || latestAssignment.disaster_id !== currentDisasterId) {
    // Jika tidak ada assignment untuk disaster ini, clear markers
    if (lastAssignmentTimestamp !== null) {
      addVolunteerMarkers([]);
      lastAssignmentTimestamp = null;
    }
  }

  // Alert feed
  const latestAlertId = alerts.length ? alerts[alerts.length - 1].id : null;
  if (latestAlertId !== lastAlertLatestId) {
    updateAlertFeed(alerts.slice(-8));
    updateAlertTable(alerts);
    lastAlertLatestId = latestAlertId;
  }

  // Audit log
  updateAuditLog(auditLog.slice(-30));

  // Agent status dari audit log
  updateAgentStatuses(auditLog);

  // Report
  if (reports.length > 0) {
    const latestReport = reports[reports.length - 1];
    const reportEl = document.getElementById('report-content');
    if (reportEl && latestReport?.content) {
      reportEl.textContent = latestReport.content;
      document.getElementById('report-container')?.classList.remove('hidden');
    }
  }

  // Priority chart
  const lastAlert = alerts[alerts.length - 1];
  if (lastAlert?.tier_breakdown) {
    updatePriorityChart(lastAlert.tier_breakdown);
  }

  // Active disaster banner
  if (disasters.some(d => d.status === 'active')) {
    const ad = disasters.find(d => d.status === 'active');
    document.getElementById('alert-banner').style.display = 'flex';
    document.getElementById('alert-banner-text').textContent =
      `Bencana Aktif — ${ad.disaster_type?.replace(/_/g, ' ').toUpperCase()}`;
    currentDisasterId = ad.id;
  } else {
    document.getElementById('alert-banner').style.display = 'none';
  }

  // Badge count
  const badge = document.getElementById('alert-badge');
  if (badge) badge.textContent = alerts.length;
  const totalCount = document.getElementById('alert-total-count');
  if (totalCount) totalCount.textContent = `${alerts.length} alert`;
}

function updateMetrics(disasters, alerts, systemState) {
  const activeDisasters = disasters.filter(d => d.status === 'active').length;
  document.getElementById('m-active-disasters').textContent = activeDisasters;

  let totalNotified = 0, totalVulnerable = 0, totalVolunteers = 0;
  alerts.forEach(a => {
    totalNotified += a.total_notified || 0;
    totalVulnerable += a.tier_breakdown?.KRITIS || 0;
  });

  document.getElementById('m-notified').textContent = totalNotified.toLocaleString();
  document.getElementById('m-vulnerable').textContent = totalVulnerable.toLocaleString();

  if (systemState.last_disaster_id) {
    // Fetch assignment count
    fetch(`${API_BASE}/api/assignments/${systemState.last_disaster_id}`)
      .then(r => {
        if (!r.ok) {
          document.getElementById('m-volunteers').textContent = '0';
          return null;
        }
        return r.json();
      })
      .then(data => {
        if (data) {
          const count = data.assignments?.length || 0;
          document.getElementById('m-volunteers').textContent = count;
        }
      })
      .catch(() => {
        document.getElementById('m-volunteers').textContent = '0';
      });
  } else {
    document.getElementById('m-volunteers').textContent = '0';
  }
}

function updateAlertFeed(alerts) {
  const feed = document.getElementById('alert-feed');
  if (!feed) return;

  if (alerts.length === 0) {
    feed.innerHTML = '<div class="empty-state">Menunggu data simulasi...</div>';
    return;
  }

  // Tampilkan 5 terbaru
  feed.innerHTML = '';
  const recent = [...alerts].reverse().slice(0, 6);
  recent.forEach(a => {
    const level = (a.alert_level || '').toLowerCase();
    const cssClass = level === 'awas' || level === 'kritis' ? 'critical' : level === 'siaga' ? 'high' : 'info';
    const time = a.sent_at ? new Date(a.sent_at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '--';

    const item = document.createElement('div');
    item.className = `alert-item ${cssClass}`;
    item.innerHTML = `
      <div class="alert-time">${time}</div>
      <div class="alert-msg">
        ${a.alert_level} — ${a.affected_districts?.join(', ') || '—'}<br>
        <span style="color:#4a5568">Ternotifikasi: ${a.total_notified || 0} warga</span>
      </div>
    `;
    feed.appendChild(item);
  });
}

function updateAlertTable(alerts) {
  const tbody = document.getElementById('alert-table-body');
  if (!tbody) return;

  if (alerts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">Jalankan simulasi untuk melihat alert</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  [...alerts].reverse().forEach(a => {
    const time = a.sent_at ? new Date(a.sent_at).toLocaleString('id-ID') : '--';
    const level = a.alert_level || '—';
    const levelColor = level === 'Awas' ? '#ff2d55' : level === 'Siaga' ? '#ff6b00' : '#ffd60a';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-family: monospace; font-size: 11px;">${time}</td>
      <td style="font-family: monospace; font-size: 11px;">${a.disaster_id || '—'}</td>
      <td><strong style="color:${levelColor}">${level}</strong></td>
      <td>${(a.affected_districts || []).join(', ') || '—'}</td>
      <td style="color:#30d158; font-weight: 600;">${a.total_notified || 0}</td>
      <td style="color:#ffd60a; font-weight: 600;">${a.tier_breakdown?.KRITIS || 0}</td>
    `;
    tbody.appendChild(tr);
  });
}

function updateAuditLog(auditLog) {
  const feed = document.getElementById('audit-feed');
  if (!feed) return;

  const latestAuditId = auditLog.length ? auditLog[auditLog.length - 1].id : null;
  if (latestAuditId && latestAuditId === lastAuditLatestId) {
    return;
  }
  lastAuditLatestId = latestAuditId;

  if (auditLog.length === 0) {
    feed.innerHTML = '<div class="empty-state">Menunggu data simulasi...</div>';
    return;
  }

  feed.innerHTML = '';
  [...auditLog].reverse().forEach(entry => {
    const time = entry.timestamp
      ? new Date(entry.timestamp).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : '--';

    const div = document.createElement('div');
    div.className = 'audit-entry';
    div.innerHTML = `
      <div class="audit-timestamp">${time}</div>
      <div>
        <div class="audit-agent">${entry.agent || '—'}</div>
        <div class="audit-action">${entry.action || '—'}</div>
      </div>
      <div class="audit-result">${(entry.result || '').substring(0, 30)}</div>
    `;
    feed.appendChild(div);
  });
}

function updateAgentStatuses(auditLog) {
  const agentActions = {};
  auditLog.forEach(entry => {
    if (entry.agent) {
      agentActions[entry.agent] = entry;
    }
  });

  const agentMap = {
    'MonitorAgent': 'monitor',
    'PredictionAgent': 'prediction',
    'EarlyWarningAgent': 'earlywarning',
    'AllocationAgent': 'allocation',
    'CommunicationAgent': 'communication',
    'OrchestratorAgent': 'orchestrator',
  };

  Object.entries(agentActions).forEach(([agentName, entry]) => {
    const key = agentMap[agentName];
    if (!key) return;

    const badge = document.getElementById(`status-${key}`);
    const log = document.getElementById(`log-${key}`);

    if (badge) {
      badge.className = 'agent-status-badge done';
      badge.textContent = 'DONE';
    }
    if (log && entry.result) {
      log.textContent = entry.result.substring(0, 80);
    }
  });
}

// ── Simulation Control ────────────────────────────────────────────────────────
async function triggerSimulation() {
  const btn = document.getElementById('btn-simulate');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Menjalankan Pipeline...';

  simStartTime = Date.now();

  // Reset pipeline viz
  setPipelineStep(-1);

  // Ubah status agen ke processing
  ['monitor', 'prediction', 'earlywarning', 'allocation', 'communication', 'orchestrator'].forEach(a => {
    const badge = document.getElementById(`status-${a}`);
    if (badge) {
      badge.className = 'agent-status-badge processing';
      badge.textContent = 'RUNNING';
    }
  });

  try {
    const response = await fetch(`${API_BASE}/api/simulate`, { method: 'POST' });
    const data = await response.json();

    if (data.status === 'started') {
      currentDisasterId = data.disaster_id;
      animatePipeline();
    }
  } catch (err) {
    alert('Error: Pastikan server FastAPI berjalan di port 8000');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">▶</span> Jalankan Simulasi Demo';
  }
}

function animatePipeline() {
  const steps = ['step-monitor', 'step-prediction', 'step-warning', 'step-allocation', 'step-communication'];
  const delays = [500, 1500, 3000, 3500, 5500];

  steps.forEach((stepId, i) => {
    setTimeout(() => {
      const el = document.getElementById(stepId);
      if (!el) return;
      el.classList.add('processing');
      const statusEl = el.querySelector('.step-status');
      if (statusEl) statusEl.textContent = 'BERJALAN...';

      setTimeout(() => {
        el.classList.remove('processing');
        el.classList.add('done');
        if (statusEl) statusEl.textContent = '✅ SELESAI';
      }, 1200);
    }, delays[i]);
  });

  // Tampilkan hasil setelah pipeline selesai
  setTimeout(async () => {
    const elapsed = ((Date.now() - simStartTime) / 1000).toFixed(1);
    await showSimResults(elapsed);

    const btn = document.getElementById('btn-simulate');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">▶</span> Jalankan Ulang';
  }, 7000);
}

async function showSimResults(elapsed) {
  document.getElementById('sim-results')?.classList.remove('hidden');
  document.getElementById('r-elapsed').textContent = elapsed + 's';

  // Coba ambil data terbaru dari API
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const status = await res.json();

    if (currentDisasterId) {
      const assignRes = await fetch(`${API_BASE}/api/assignments/${currentDisasterId}`);
      if (assignRes.ok) {
        const assignments = await assignRes.json();
        document.getElementById('r-volunteers').textContent =
          assignments.assignments?.length || '—';
      } else if (assignRes.status === 404) {
        console.log('[INFO] Assignment tidak ditemukan untuk disaster:', currentDisasterId);
        document.getElementById('r-volunteers').textContent = '—';
      } else {
        console.error('[ERROR] Assignment fetch error:', assignRes.status);
      }
    }

    const alertRes = await fetch(`${API_BASE}/api/alerts/recent`);
    if (alertRes.ok) {
      const alerts = await alertRes.json();
      const latest = alerts[0];
      if (latest) {
        document.getElementById('r-notified').textContent = latest.total_notified || '—';
        document.getElementById('r-critical').textContent = latest.tier_breakdown?.KRITIS || '—';
      }
    }
  } catch (e) {
    console.error('[ERROR] showSimResults error:', e);
    document.getElementById('r-notified').textContent = '—';
    document.getElementById('r-critical').textContent = '—';
    document.getElementById('r-volunteers').textContent = '—';
  }

  // Ambil laporan
  try {
    const reportRes = await fetch(`${API_BASE}/api/reports`);
    if (reportRes.ok) {
      const reports = await reportRes.json();
      if (reports.length > 0) {
        document.getElementById('report-content').textContent = reports[0].content || '—';
        document.getElementById('report-container')?.classList.remove('hidden');
      }
    }
  } catch (e) {
    console.error('[ERROR] Report fetch error:', e);
  }
}

async function confirmAssignment() {
  if (!currentDisasterId) {
    alert('⚠️ Jalankan simulasi terlebih dahulu.');
    return;
  }
  
  console.log('[DEBUG] currentDisasterId:', currentDisasterId);
  
  try {
    const url = `${API_BASE}/api/coordinator/confirm-assignment/${currentDisasterId}?coordinator_id=KOORDINATOR_DEMO`;
    console.log('[DEBUG] Memanggil URL:', url);
    
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    console.log('[DEBUG] Response status:', res.status, 'Data:', data);
    
    if (!res.ok) {
      const errorMessage = data.detail || data.message || 'Gagal mengkonfirmasi penugasan.';
      console.log('[DEBUG] Error message:', errorMessage);
      alert(`⚠️ ${errorMessage}`);
      return;
    }
    
    const successMessage = data.message || 'Konfirmasi berhasil.';
    console.log('[DEBUG] Success message:', successMessage);
    alert(`✅ ${successMessage}`);
    document.getElementById('btn-confirm').textContent = '✅ Sudah Dikonfirmasi';
    document.getElementById('btn-confirm').disabled = true;
  } catch (e) {
    console.error('[DEBUG] Catch error:', e);
    alert('Error konfirmasi: ' + (e.message || 'Tidak diketahui'));
  }
}


function setPipelineStep(stepIndex) {
  const steps = ['step-monitor', 'step-prediction', 'step-warning', 'step-allocation', 'step-communication'];
  steps.forEach((id, i) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('processing', 'done');
    const statusEl = el.querySelector('.step-status');
    if (statusEl) statusEl.textContent = 'Menunggu';
  });
}

async function resetSimulation() {
  const resetBtn = document.getElementById('btn-reset');
  resetBtn.disabled = true;
  resetBtn.textContent = '⏳ Reset...';

  try {
    const response = await fetch(`${API_BASE}/api/reset-simulation`, { method: 'POST' });
    if (response.ok) {
      currentDisasterId = null;
      lastRiskMapTimestamp = null;
      lastAuditLatestId = null;
      lastAlertLatestId = null;
      lastAssignmentTimestamp = null;
      userInteractedMap = false;
      setPipelineStep(-1);
      document.getElementById('sim-results')?.classList.add('hidden');
      document.getElementById('report-container')?.classList.add('hidden');
      document.getElementById('alert-banner').style.display = 'none';

      const btn = document.getElementById('btn-simulate');
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">▶</span> Jalankan Simulasi Demo';

      ['monitor', 'prediction', 'earlywarning', 'allocation', 'communication', 'orchestrator'].forEach(a => {
        const badge = document.getElementById(`status-${a}`);
        if (badge) { badge.className = 'agent-status-badge idle'; badge.textContent = 'IDLE'; }
        const log = document.getElementById(`log-${a}`);
        if (log) log.textContent = 'Menunggu trigger...';
      });

      document.getElementById('alert-feed').innerHTML = '<div class="empty-state">Menunggu data simulasi...</div>';
      document.getElementById('alert-table-body').innerHTML = '<tr><td colspan="6" class="empty-cell">Jalankan simulasi untuk melihat alert</td></tr>';
      document.getElementById('audit-feed').innerHTML = '<div class="empty-state">Menunggu data simulasi...</div>';

      // Clear metrik
      document.getElementById('m-active-disasters').textContent = '0';
      document.getElementById('m-notified').textContent = '0';
      document.getElementById('m-vulnerable').textContent = '0';
      document.getElementById('m-volunteers').textContent = '0';
      if (typeof updateRiskMap === 'function') {
        updateRiskMap({ features: [] });
      }
      if (typeof addVolunteerMarkers === 'function') {
        addVolunteerMarkers([]);
      }
      if (typeof map !== 'undefined' && map) {
        map.setView(MAP_CENTER, MAP_ZOOM);
      }

      // Reset button states
      document.getElementById('btn-confirm').textContent = '✓ Konfirmasi Penugasan';
      document.getElementById('btn-confirm').disabled = false;

      if (sseSource) {
        sseSource.close();
        sseSource = null;
      }
      startSSE();
    } else {
      alert('Reset simulasi gagal. Silakan coba lagi.');
    }
  } catch (err) {
    alert('Reset error: ' + err.message);
  } finally {
    resetBtn.disabled = false;
    resetBtn.textContent = '↺ Reset';
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  startSSE();
});
