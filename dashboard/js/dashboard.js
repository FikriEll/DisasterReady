/**
 * PANTARA Bencana — Main Dashboard Controller
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
let lastReportId = null;

// ── View Navigation ────────────────────────────────────────────────────────────
function showView(viewName) {
  document.querySelectorAll('.view').forEach(v => {
    v.classList.remove('flex');
    v.classList.add('hidden');
  });
  document.querySelectorAll('.nav-link').forEach(n => {
    n.classList.remove('bg-secondary-container', 'text-on-secondary-container');
    n.classList.add('text-on-surface-variant');
  });

  const view = document.getElementById(`view-${viewName}`);
  const navBtn = document.getElementById(`nav-${viewName}`);

  if (view) {
    view.classList.remove('hidden');
    view.classList.add('flex');
  }
  if (navBtn) {
    navBtn.classList.remove('text-on-surface-variant');
    navBtn.classList.add('bg-secondary-container', 'text-on-secondary-container');
  }

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
      
      // Auto-open panel if this is a new report
      if (latestReport.id && latestReport.id !== lastReportId) {
        lastReportId = latestReport.id;
        // Don't auto-open immediately on page load, only if there's a running simulation or we explicitly clicked
        if (currentDisasterId && simStartTime) {
          openReport();
        }
      }
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
    feed.innerHTML = '<div class="text-on-surface-variant text-sm text-center py-8">Menunggu data simulasi...</div>';
    return;
  }

  feed.innerHTML = '';
  const recent = [...alerts].reverse().slice(0, 6);
  recent.forEach(a => {
    const level = (a.alert_level || '').toLowerCase();
    
    let bgClass, borderClass, iconColor, textColor, iconName;
    if (level === 'awas' || level === 'kritis') {
      bgClass = 'bg-[#fef9c3]'; borderClass = 'border-[#fef08a]';
      iconColor = 'text-[#ca8a04]'; textColor = 'text-[#854d0e]';
      iconName = 'error';
    } else if (level === 'siaga') {
      bgClass = 'bg-[#fee2e2]'; borderClass = 'border-[#fecaca]';
      iconColor = 'text-primary'; textColor = 'text-primary';
      iconName = 'emergency';
    } else {
      bgClass = 'bg-[#ffedd5]'; borderClass = 'border-[#fed7aa]';
      iconColor = 'text-[#ea580c]'; textColor = 'text-[#9a3412]';
      iconName = 'warning';
    }
    
    const formatDistrict = (d) => {
      if (!d) return '';
      return d.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    };
    const formattedDistricts = (a.affected_districts || []).map(formatDistrict).join(', ') || '—';

    const time = a.sent_at ? new Date(a.sent_at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '--';

    const item = document.createElement('div');
    item.className = `p-3 border ${borderClass} ${bgClass} rounded-lg mb-2`;
    item.innerHTML = `
      <div class="flex items-center gap-2 mb-1">
        <span class="material-symbols-outlined ${iconColor}" style="font-variation-settings: 'FILL' 1;">${iconName}</span>
        <span class="font-label-md text-label-md ${textColor} uppercase tracking-wider">${a.alert_level}</span>
      </div>
      <p class="font-body-md text-body-md text-on-surface-variant">
        Wilayah Terdampak: <b>${formattedDistricts}</b><br>
        Ternotifikasi: <b>${a.total_notified || 0}</b> warga rentan.
      </p>
      <span class="text-status-sm font-status-sm text-on-surface-variant block mt-2">${time}</span>
    `;
    feed.appendChild(item);
  });
}

function updateAlertTable(alerts) {
  const tbody = document.getElementById('alert-table-body');
  if (!tbody) return;

  if (alerts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-on-surface-variant">Jalankan simulasi untuk melihat alert</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  [...alerts].reverse().forEach(a => {
    const time = a.sent_at ? new Date(a.sent_at).toLocaleString('id-ID') : '--';
    const level = a.alert_level || '—';
    
    let levelBadge = '';
    if (level === 'Awas') levelBadge = '<span class="px-2 py-1 bg-secondary-fixed text-on-secondary-fixed rounded text-status-sm font-status-sm">Awas</span>';
    else if (level === 'Siaga') levelBadge = '<span class="px-2 py-1 bg-[#ffedd5] text-[#9a3412] rounded text-status-sm font-status-sm">Siaga</span>';
    else levelBadge = '<span class="px-2 py-1 bg-surface-variant text-on-surface-variant rounded text-status-sm font-status-sm">Waspada</span>';

    const tr = document.createElement('tr');
    tr.className = 'border-b border-outline-variant hover:bg-surface-container-highest transition-colors';
    
    // Calculate a mock score out of 100 based on KRITIS
    const vulnScore = Math.min(100, Math.max(10, (a.tier_breakdown?.KRITIS || 0)));
    let scoreColor = vulnScore > 70 ? 'bg-primary' : (vulnScore > 40 ? 'bg-[#ea580c]' : 'bg-outline');
    let textColor = vulnScore > 70 ? 'text-primary' : (vulnScore > 40 ? 'text-[#ea580c]' : 'text-on-surface-variant');
    let scoreLabel = vulnScore > 70 ? 'High' : (vulnScore > 40 ? 'Med' : 'Low');

    const formatDistrict = (d) => {
      if (!d) return '';
      return d.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    };
    const formattedDistricts = (a.affected_districts || []).map(formatDistrict).join(', ') || '—';

    tr.innerHTML = `
      <td class="p-3">${a.disaster_id || '—'}</td>
      <td class="p-3">${formattedDistricts}</td>
      <td class="p-3">${levelBadge}</td>
      <td class="p-3">
        <div class="flex items-center gap-2">
        <div class="w-full bg-surface-variant rounded-full h-2 max-w-[100px]">
        <div class="${scoreColor} h-2 rounded-full" style="width: ${vulnScore}%"></div>
        </div>
        <span class="text-status-sm font-status-sm ${textColor}">${scoreLabel} (${vulnScore})</span>
        </div>
      </td>
      <td class="p-3"><span class="text-secondary font-medium">Processing</span></td>
      <td class="p-3">
        <button onclick="openReport()" class="text-secondary border border-secondary px-3 py-1 rounded text-status-sm font-status-sm hover:bg-secondary-container hover:text-on-secondary-container transition-colors flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">smart_toy</span> AI Report</button>
      </td>
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
    div.className = 'p-3 bg-surface-container-highest rounded-lg border border-outline-variant';
    div.innerHTML = `
      <div class="flex items-center justify-between mb-1">
        <span class="font-label-md text-label-md text-primary uppercase">${entry.agent || 'SYSTEM'}</span>
        <span class="text-status-sm font-status-sm text-on-surface-variant">${time}</span>
      </div>
      <div class="font-body-md text-body-md text-on-surface mb-1"><strong>${entry.action || '—'}</strong></div>
      <div class="font-body-md text-body-md text-on-surface-variant break-words">${(entry.result || '')}</div>
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
    if (badge) {
      badge.className = 'px-2 py-1 rounded-full bg-secondary-container text-on-secondary-container transition-colors border border-secondary';
    }
  });
}

// ── Simulation Control ────────────────────────────────────────────────────────
async function triggerSimulation() {
  const btn = document.getElementById('btn-simulate');
  btn.disabled = true;
  btn.textContent = 'DEPLOYING...';

  simStartTime = Date.now();

  ['monitor', 'prediction', 'earlywarning', 'allocation', 'communication'].forEach(a => {
    const badge = document.getElementById(`status-${a}`);
    if (badge) {
      badge.className = 'px-2 py-1 rounded-full bg-[#fef9c3] text-[#854d0e] transition-colors border border-[#fef08a] animate-pulse';
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
    btn.textContent = 'DEPLOY RAPID RESPONSE';
  }
}

function animatePipeline() {
  // Tampilkan hasil setelah pipeline selesai
  setTimeout(async () => {
    const elapsed = ((Date.now() - simStartTime) / 1000).toFixed(1);
    await showSimResults(elapsed);

    const btn = document.getElementById('btn-simulate');
    btn.disabled = false;
    btn.textContent = 'DEPLOY RAPID RESPONSE';
  }, 7000);
}

async function showSimResults(elapsed) {
  const simToast = document.getElementById('sim-results');
  if (simToast) {
    simToast.classList.remove('hidden');
    // Animate in
    setTimeout(() => {
      simToast.classList.remove('translate-y-20', 'opacity-0');
      simToast.classList.add('translate-y-0', 'opacity-100');
    }, 10);
  }
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
        const reportEl = document.getElementById('report-content');
        if (reportEl) {
          // Parse as simple markdown (if needed) or keep as raw text
          reportEl.textContent = reports[reports.length - 1].content || '—';
          // Auto-open report panel to showcase the feature
          openReport();
        }
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
    
    // Animate button success
    const btn = document.getElementById('btn-confirm');
    if (btn) {
      btn.innerHTML = '<span class="material-symbols-outlined text-[18px]">check_circle</span> DEPLOYED';
      btn.classList.replace('bg-secondary', 'bg-[#15803d]'); // green
      
      // Create a temporary toast
      const toast = document.createElement('div');
      toast.className = 'fixed top-20 left-1/2 -translate-x-1/2 bg-inverse-surface text-inverse-on-surface px-6 py-3 rounded-full shadow-2xl z-[100] font-label-md flex items-center gap-2 animate-bounce';
      toast.innerHTML = '<span class="material-symbols-outlined text-[#4ade80]">verified</span> Relawan telah dikerahkan ke lapangan.';
      document.body.appendChild(toast);
      
      setTimeout(() => {
        toast.remove();
        btn.innerHTML = 'CONFIRM FIELD OP';
        btn.classList.replace('bg-[#15803d]', 'bg-secondary');
      }, 3000);
    }
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
      btn.textContent = 'DEPLOY RAPID RESPONSE';

      ['monitor', 'prediction', 'earlywarning', 'allocation', 'communication'].forEach(a => {
        const badge = document.getElementById(`status-${a}`);
        if (badge) { 
          badge.className = 'px-2 py-1 rounded-full bg-surface-variant text-on-surface-variant transition-colors border border-outline-variant'; 
        }
      });

      document.getElementById('alert-feed').innerHTML = '<div class="text-on-surface-variant text-sm text-center py-8">Menunggu data simulasi...</div>';
      document.getElementById('alert-table-body').innerHTML = '<tr><td colspan="6" class="p-4 text-center text-on-surface-variant">Jalankan simulasi untuk melihat alert</td></tr>';
      document.getElementById('audit-feed').innerHTML = '<div class="text-on-surface-variant text-sm text-center py-8">Menunggu log sistem...</div>';
      
      const reportEl = document.getElementById('report-content');
      if (reportEl) reportEl.textContent = 'Menunggu laporan...';

      // Clear metrik
      document.getElementById('m-active-disasters').textContent = '0';
      document.getElementById('m-notified').textContent = '0';
      document.getElementById('m-vulnerable').textContent = '0';
      document.getElementById('m-volunteers').textContent = '0';
      if (typeof updateRiskMap === 'function') {
        updateRiskMap({ type: "FeatureCollection", features: [] });
      }
      if (typeof addVolunteerMarkers === 'function') {
        addVolunteerMarkers([]);
      }
      if (typeof map !== 'undefined' && map) {
        map.setView(MAP_CENTER, MAP_ZOOM);
      }

      // Reset button states
      const confirmBtn = document.getElementById('btn-confirm');
      if (confirmBtn) {
        confirmBtn.innerHTML = 'CONFIRM FIELD OP';
        confirmBtn.disabled = false;
        confirmBtn.classList.replace('bg-[#15803d]', 'bg-secondary');
      }

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
    resetBtn.textContent = 'RESET OP';
  }
}

// ── AI Report UI ──────────────────────────────────────────────────────────────
function openReport() {
  const panel = document.getElementById('report-container');
  if (panel) {
    panel.classList.remove('translate-x-full');
    panel.classList.add('translate-x-0');
  }
}

function closeReport() {
  const panel = document.getElementById('report-container');
  if (panel) {
    panel.classList.remove('translate-x-0');
    panel.classList.add('translate-x-full');
  }
}

function triggerOverride() {
  const toast = document.createElement('div');
  toast.className = 'fixed top-20 left-1/2 -translate-x-1/2 bg-error text-on-error px-6 py-3 rounded-full shadow-2xl z-[100] font-label-md flex items-center gap-2 animate-pulse';
  toast.innerHTML = '<span class="material-symbols-outlined">warning</span> SYSTEM OVERRIDE PROTOCOL INITIATED';
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.remove();
  }, 3000);
}


// ── Theme Toggle ──────────────────────────────────────────────────────────────
function initTheme() {
  const savedTheme = localStorage.getItem('pantara_bencana_theme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
  }
  updateThemeIcon();
}

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('pantara_bencana_theme', newTheme);
  updateThemeIcon();
}

function updateThemeIcon() {
  const theme = document.documentElement.getAttribute('data-theme');
  const iconEl = document.getElementById('theme-icon');
  if (iconEl) {
    iconEl.textContent = theme === 'dark' ? '☀️' : '🌙';
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  startSSE();
});
