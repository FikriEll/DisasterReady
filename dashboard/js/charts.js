/**
 * DisasterReady — Charts Module
 * Visualisasi data prioritas notifikasi dan metrik dampak.
 * Library: Chart.js v4 | https://www.chartjs.org
 */

let priorityChart = null;

const CHART_COLORS = {
  kritis: 'rgba(255, 45, 85, 0.85)',
  tinggi: 'rgba(255, 107, 0, 0.8)',
  sedang: 'rgba(255, 214, 10, 0.75)',
  rendah: 'rgba(48, 209, 88, 0.7)',
};

function initPriorityChart() {
  const ctx = document.getElementById('priorityChart');
  if (!ctx) return;

  priorityChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['KRITIS', 'TINGGI', 'SEDANG', 'RENDAH'],
      datasets: [{
        data: [0, 0, 0, 0],
        backgroundColor: Object.values(CHART_COLORS),
        borderColor: 'transparent',
        hoverOffset: 6,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#8b9ab0',
            font: { family: 'Inter', size: 10 },
            padding: 12,
            usePointStyle: true,
            pointStyleWidth: 8,
          },
        },
        tooltip: {
          backgroundColor: 'rgba(17, 19, 24, 0.95)',
          titleColor: '#f0f2f5',
          bodyColor: '#8b9ab0',
          borderColor: 'rgba(255,255,255,0.08)',
          borderWidth: 1,
          callbacks: {
            label: (c) => ` ${c.label}: ${c.parsed} warga`,
          },
        },
      },
    },
  });
}

function updatePriorityChart(breakdown) {
  if (!priorityChart) initPriorityChart();
  if (!priorityChart) return;

  const data = [
    breakdown?.KRITIS || 0,
    breakdown?.TINGGI || 0,
    breakdown?.SEDANG || 0,
    breakdown?.RENDAH || 0,
  ];

  priorityChart.data.datasets[0].data = data;
  priorityChart.update('active');
}

document.addEventListener('DOMContentLoaded', initPriorityChart);
