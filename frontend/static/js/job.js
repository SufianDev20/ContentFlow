// job.js
// FIXED: removed local apiFetch/authHeaders/LOGIN_URL redirect. Uses the
// shared apiFetch from common.js (cookie-based, refresh-and-retry on 401).
// Matches apps.stats.models.Output: flat fields, no nested "metrics" object.

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function renderRatingWidget(outputId, currentRating) {
    let stars = '';
    for (let i = 1; i <= 5; i++) {
        const filled = currentRating && i <= currentRating ? 'filled' : '';
        stars += `<span class="star ${filled}" data-output-id="${outputId}" data-value="${i}" role="button" aria-label="Rate ${i} of 5"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8z"/></svg></span>`;
    }
    return `<div class="rating-widget">${stars}</div>`;
}

function renderScheduleControl(output, scheduledEmail) {
    if (output.format !== 'email') return '';
    if (scheduledEmail && scheduledEmail.status === 'scheduled') {
        return `
      <div class="output-schedule-status" data-output-id="${output.id}">
        <span class="text-sm">Scheduled for ${formatDateTime(scheduledEmail.scheduled_for)}</span>
        <button class="btn btn-secondary btn-sm cancel-schedule-btn" data-scheduled-id="${scheduledEmail.id}">Cancel</button>
      </div>`;
    }
    const scheduleBtn = `<button class="btn btn-secondary btn-sm schedule-btn" data-output-id="${output.id}">Schedule</button>`;
    if (scheduledEmail && scheduledEmail.status === 'sent') {
        return `
      <div class="output-schedule-status" data-output-id="${output.id}">
        <span class="text-sm">Sent ${formatDateTime(scheduledEmail.sent_at || scheduledEmail.scheduled_for)}</span>
        ${scheduleBtn}
      </div>`;
    }
    if (scheduledEmail && scheduledEmail.status === 'failed') {
        return `
      <div class="output-schedule-status" data-output-id="${output.id}">
        <span class="text-sm">Send failed${scheduledEmail.error_message ? ': ' + escapeHtml(scheduledEmail.error_message) : ''}</span>
        ${scheduleBtn}
      </div>`;
    }
    return scheduleBtn;
}

function renderOutputCard(output, scheduledEmail) {
    const card = document.createElement('div');
    card.className = 'output-card';

    const quality = output.quality_score ?? 0;
    const latency = output.latency_ms ?? 0;
    const speed = output.tokens_per_second ?? 0;
    const tokens = output.tokens_generated ?? 0;

    card.innerHTML = `
    <div class="output-card-header">
      <span class="output-card-format">${(output.format || '').replace('_', ' ')}</span>
      <button class="copy-btn" data-text="${escapeHtml(output.text || '')}">Copy</button>
    </div>
    <p class="output-card-body">${escapeHtml(output.text || '')}</p>
    <details class="output-metrics">
      <summary>Metrics</summary>
      <div class="output-metrics-row">
        Quality: ${quality}/100 ·
        Tokens: ${tokens} ·
        Latency: ${latency}ms ·
        Speed: ${speed} tok/s
      </div>
    </details>
    ${renderRatingWidget(output.id, output.user_rating)}
    ${renderScheduleControl(output, scheduledEmail)}
  `;

    card.querySelector('.copy-btn').addEventListener('click', (e) => {
        navigator.clipboard.writeText(e.target.dataset.text);
        e.target.textContent = 'Copied!';
        setTimeout(() => { e.target.textContent = 'Copy'; }, 1500);
    });

    const scheduleBtn = card.querySelector('.schedule-btn');
    if (scheduleBtn) {
        scheduleBtn.addEventListener('click', () => openScheduleModal(output));
    }

    const cancelBtn = card.querySelector('.cancel-schedule-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', async (e) => {
            const scheduledId = e.target.dataset.scheduledId;
            const result = await apiFetch(`/scheduled-emails/${scheduledId}/cancel/`, { method: 'POST' });
            if (result && !result.error) loadJob();
        });
    }

    return card;
}

let scheduleModalOutput = null;
const MIN_SCHEDULE_LEAD_MS = 2 * 60 * 1000;

function showScheduleError(message) {
    const el = document.getElementById('schedule-error');
    el.textContent = message;
    el.classList.toggle('visible', Boolean(message));
}

function openScheduleModal(output) {
    scheduleModalOutput = output;
    showScheduleError('');
    document.getElementById('schedule-recipients').value = '';
    document.getElementById('schedule-subject').value = '';
    document.getElementById('schedule-content').value = output.text || '';
    // Earliest allowed send time: 2 min out, so the click and the server check both have margin.
    const earliest = new Date(Date.now() + MIN_SCHEDULE_LEAD_MS);
    earliest.setSeconds(0, 0);
    const minLocal = new Date(earliest - earliest.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    const timeInput = document.getElementById('schedule-time');
    timeInput.min = minLocal;
    timeInput.value = '';
    document.getElementById('schedule-modal-overlay').classList.remove('hidden');
}

function closeScheduleModal() {
    scheduleModalOutput = null;
    document.getElementById('schedule-modal-overlay').classList.add('hidden');
}

document.getElementById('schedule-modal-close').addEventListener('click', closeScheduleModal);

document.getElementById('schedule-save-btn').addEventListener('click', async () => {
    showScheduleError('');

    const recipients = document.getElementById('schedule-recipients').value
        .split(',').map((r) => r.trim()).filter(Boolean);
    const subject = document.getElementById('schedule-subject').value.trim();
    const editedContent = document.getElementById('schedule-content').value;
    const scheduledFor = document.getElementById('schedule-time').value;

    if (recipients.length === 0 || !subject || !scheduledFor) {
        showScheduleError('Recipients, subject, and send time are required.');
        return;
    }

    const scheduledDate = new Date(scheduledFor);
    if (scheduledDate.getTime() < Date.now() + MIN_SCHEDULE_LEAD_MS) {
        showScheduleError('Pick a send time at least 2 minutes from now.');
        return;
    }

    const result = await apiFetch('/scheduled-emails/', {
        method: 'POST',
        body: JSON.stringify({
            output: scheduleModalOutput.id,
            recipients,
            subject,
            edited_content: editedContent,
            scheduled_for: scheduledDate.toISOString()
        })
    });

    if (!result || result.error) {
        showScheduleError((result && result.error) || 'Could not schedule email.');
        return;
    }

    closeScheduleModal();
    const toast = document.getElementById('schedule-success');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2500);
    loadJob();
});

document.addEventListener('click', async (e) => {
    if (!e.target.classList.contains('star')) return;
    const outputId = e.target.dataset.outputId;
    const rating = parseInt(e.target.dataset.value, 10);
    await apiFetch(`/outputs/${outputId}/rate/`, {
        method: 'PATCH',
        body: JSON.stringify({ user_rating: rating })
    });

    const widget = e.target.closest('.rating-widget');
    widget.querySelectorAll('.star').forEach((star) => {
        const value = parseInt(star.dataset.value, 10);
        star.classList.toggle('filled', value <= rating);
    });
});

function formatDate(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatDateTime(iso) {
    return new Date(iso).toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
    });
}

async function loadJob() {
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get('id');

    if (!jobId) {
        document.getElementById('job-error').textContent = 'No job specified.';
        document.getElementById('job-error').classList.add('visible');
        return;
    }

    const job = await apiFetch(`/jobs/${jobId}/`);

    if (!job || job.error) {
        document.getElementById('job-error').textContent = 'Job not found.';
        document.getElementById('job-error').classList.add('visible');
        return;
    }

    document.getElementById('job-model').textContent = job.model;
    document.getElementById('job-date').textContent = formatDate(job.created_at);

    const container = document.getElementById('outputs-container');
    const outputs = job.outputs || [];
    container.innerHTML = '';

    if (outputs.length === 0) {
        container.innerHTML = '<div class="empty-state">No outputs for this job.</div>';
        return;
    }

    // API returns newest first; keep the latest non-cancelled entry per output.
    const scheduledResult = await apiFetch('/scheduled-emails/');
    const scheduledByOutputId = {};
    if (scheduledResult && !scheduledResult.error) {
        (scheduledResult.results || scheduledResult || []).forEach((s) => {
            if (s.status !== 'cancelled' && !scheduledByOutputId[s.output]) {
                scheduledByOutputId[s.output] = s;
            }
        });
    }

    outputs.forEach((output) => container.appendChild(renderOutputCard(output, scheduledByOutputId[output.id])));
}

loadJob();