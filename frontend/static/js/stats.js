// stats.js
// Populates the Stats page: summary cards, efficiency table, and quality chart.
// Matches apps.stats.views.SummaryStatsView and ModelStatsView response shapes exactly.

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartPalette() {
    return [1, 2, 3, 4, 5].map((n) => cssVar(`--chart-${n}`));
}

function chartTheme() {
    return { text: cssVar('--muted'), grid: cssVar('--chart-grid') };
}

let qualityChartInstance = null;
let sendStatusChartInstance = null;

function formatModelName(model) {
    if (!model) return '—';
    // Strip vendor prefix e.g. "openai/gpt-4o" -> "gpt-4o"
    const parts = model.split('/');
    return parts[parts.length - 1];
}

function formatFormatName(format) {
    if (!format) return '—';
    return format.replace(/_/g, ' ');
}

function renderSummary(summary) {
    document.getElementById('stat-total-jobs').textContent = summary.total_jobs;
    document.getElementById('stat-total-outputs').textContent = summary.total_outputs;
    document.getElementById('stat-best-model').textContent = formatModelName(summary.best_model_overall);
    document.getElementById('stat-avg-quality').textContent = `${summary.avg_quality_score}`;
}

function renderEfficiencyTable(rows) {
    const tbody = document.getElementById('stats-tbody');
    tbody.innerHTML = '';

    const byModel = {};
    rows.forEach((row) => {
        const key = row.model;
        if (!byModel[key]) {
            byModel[key] = {
                model: row.model,
                totalLatency: 0,
                totalTokensPerSec: 0,
                totalGenerations: 0
            };
        }
        // Weight by total_generations so a format with more runs
        // contributes proportionally more to the model's average.
        byModel[key].totalLatency += row.avg_latency_ms * row.total_generations;
        byModel[key].totalTokensPerSec += row.avg_tokens_per_second * row.total_generations;
        byModel[key].totalGenerations += row.total_generations;
    });

    Object.values(byModel).forEach((data) => {
        const avgLatency = data.totalGenerations
            ? Math.round(data.totalLatency / data.totalGenerations)
            : 0;
        const avgTokensPerSec = data.totalGenerations
            ? Math.round(data.totalTokensPerSec / data.totalGenerations)
            : 0;

        // Determine status based on latency (simple heuristic)
        const status = avgLatency > 3000 ? 'Degraded' : 'Active';
        const statusClass = status === 'Active' ? 'status-active' : 'status-degraded';

        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td>${formatModelName(data.model)}</td>
      <td class="num">${avgLatency}</td>
      <td class="num">${avgTokensPerSec}</td>
      <td class="num">${data.totalGenerations}</td>
      <td class="${statusClass}">${status}</td>
    `;
        tbody.appendChild(tr);
    });
}

function renderChart(rows) {
    const canvas = document.getElementById('qualityChart');
    const emptyState = document.getElementById('empty-state');

    if (!canvas) return;
    if (typeof Chart === 'undefined') {
        emptyState.textContent = 'Chart library could not be loaded. Please refresh and try again.';
        emptyState.classList.remove('hidden');
        return;
    }

    if (qualityChartInstance) {
        qualityChartInstance.destroy();
    }

    const byModelFormat = {};
    const formatSet = new Set();

    rows.forEach((row) => {
        const modelKey = formatModelName(row.model);
        const formatKey = formatFormatName(row.format);
        formatSet.add(formatKey);
        if (!byModelFormat[modelKey]) {
            byModelFormat[modelKey] = {};
        }
        byModelFormat[modelKey][formatKey] = row.avg_quality_score;
    });

    const models = Object.keys(byModelFormat);
    const formats = Array.from(formatSet);

    if (models.length === 0 || formats.length === 0) {
        emptyState.textContent = 'No chartable quality data found yet.';
        emptyState.classList.remove('hidden');
        return;
    }

    const colors = chartPalette();
    const theme = chartTheme();

    const datasets = formats.map((format, index) => ({
        label: format,
        data: models.map((model) => byModelFormat[model][format] || 0),
        backgroundColor: colors[index % colors.length],
        borderRadius: 0
    }));

    qualityChartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: models,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'start',
                    labels: {
                        color: theme.text,
                        boxWidth: 10,
                        boxHeight: 10,
                        font: { size: 12 }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: theme.text, font: { size: 12 } },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { color: theme.text, font: { size: 12 }, stepSize: 25 },
                    grid: { color: theme.grid }
                }
            }
        }
    });
}

function renderSendStatusChart(statusCounts) {
    const canvas = document.getElementById('sendStatusChart');
    if (!canvas || typeof Chart === 'undefined') return;

    if (sendStatusChartInstance) {
        sendStatusChartInstance.destroy();
    }

    const labels = Object.keys(statusCounts);
    const data = Object.values(statusCounts);

    sendStatusChartInstance = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: chartPalette(),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '68%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: chartTheme().text, boxWidth: 10, boxHeight: 10, font: { size: 12 } }
                }
            }
        }
    });
}

function renderSchedulingActivityTable(activity) {
    const tbody = document.getElementById('scheduling-activity-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    activity.forEach((row) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td>${row.day}</td>
      <td class="num">${row.scheduled_count}</td>
      <td class="num">${row.sent_count}</td>
    `;
        tbody.appendChild(tr);
    });
}

async function loadSchedulingStats() {
    const data = await window.apiFetch('/stats/scheduling/');
    if (!data || data.error) return;
    renderSendStatusChart(data.status_counts);
    renderSchedulingActivityTable(data.activity);
}

async function loadStats() {
    const [summary, modelRows] = await Promise.all([
        window.apiFetch('/stats/summary/'),
        window.apiFetch('/stats/models/')
    ]);

    if (!summary || summary.error || !modelRows || modelRows.error) {
        document.getElementById('empty-state').textContent = 'Could not load stats. Try again.';
        document.getElementById('empty-state').classList.remove('hidden');
        document.getElementById('stats-content').classList.add('hidden');
        return;
    }

    if (!Array.isArray(modelRows) || modelRows.length === 0) {
        renderSummary(summary);
        document.getElementById('empty-state').textContent = 'No generated outputs found for this account yet.';
        document.getElementById('empty-state').classList.remove('hidden');
        document.getElementById('stats-content').classList.add('hidden');
        return;
    }

    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('stats-content').classList.remove('hidden');

    renderSummary(summary);
    renderEfficiencyTable(modelRows);
    renderChart(modelRows);
}

loadStats();
loadSchedulingStats();

// Charts read their colours from CSS variables, so redraw them when the theme changes.
document.addEventListener('themechange', () => {
    if (!document.getElementById('stats-content').classList.contains('hidden')) {
        loadStats();
        loadSchedulingStats();
    }
});
