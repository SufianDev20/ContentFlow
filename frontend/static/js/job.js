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

function renderScheduledOutputCard(output, scheduledEmail) {
    const card = renderOutputCard(output, renderScheduleControl(output, scheduledEmail));

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

    outputs.forEach((output) => container.appendChild(renderScheduledOutputCard(output, scheduledByOutputId[output.id])));
}

loadJob();