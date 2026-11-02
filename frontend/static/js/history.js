// FIXED: removed local apiFetch/authHeaders. Uses the shared apiFetch
// from common.js, which sends the httpOnly cookie via credentials:
// 'include' and retries once after a refresh on 401.

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function formatDate(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function badgeClass(status) {
    if (status === 'complete') return 'badge badge-status-complete';
    if (status === 'failed') return 'badge badge-status-failed';
    return 'badge badge-status-processing';
}

function renderPagination(count, page, pageSize = 20) {
    const totalPages = Math.max(1, Math.ceil(count / pageSize));
    const startItem = count === 0 ? 0 : (page - 1) * pageSize + 1;
    const endItem = Math.min(page * pageSize, count);

    const infoContainer = document.getElementById('pagination-info');
    if (infoContainer) {
        infoContainer.textContent = count === 0 ? '' : `Showing ${startItem} to ${endItem} of ${count} results`;
    }

    const controlsContainer = document.getElementById('pagination-controls');
    if (!controlsContainer) return;
    controlsContainer.innerHTML = '';

    if (count === 0 || totalPages <= 1) return;

    const prevBtn = document.createElement('button');
    prevBtn.className = 'pagination-btn';
    prevBtn.textContent = 'Previous';
    prevBtn.disabled = page === 1;
    prevBtn.addEventListener('click', () => loadHistory(page - 1));
    controlsContainer.appendChild(prevBtn);

    const nextBtn = document.createElement('button');
    nextBtn.className = 'pagination-btn';
    nextBtn.textContent = 'Next';
    nextBtn.disabled = page === totalPages;
    nextBtn.addEventListener('click', () => loadHistory(page + 1));
    controlsContainer.appendChild(nextBtn);
}

async function loadHistory(page = 1) {
    const result = await apiFetch(`/jobs/?page=${page}`);
    if (!result || result.error) return;

    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = '';

    if (!result.results || result.results.length === 0) {
        document.getElementById('empty-state').classList.remove('hidden');
        renderPagination(0, page);
        return;
    }

    document.getElementById('empty-state').classList.add('hidden');

    result.results.forEach((job) => {
        const row = document.createElement('tr');
        row.className = 'clickable';
        row.innerHTML = `
      <td>${formatDate(job.created_at)}</td>
      <td>${job.id.substring(0, 8)}</td>
      <td>${escapeHtml(job.model)}</td>
      <td class="num">${job.word_count}</td>
      <td><span class="${badgeClass(job.status)}">${job.status}</span></td>
      <td class="actions">
        <button class="btn btn-secondary btn-sm view-btn" onclick="event.stopPropagation(); window.location.href = '${JOB_URL_BASE}?id=${job.id}'">View</button>
        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteJob('${job.id}')">Delete</button>
      </td>
    `;
        row.addEventListener('click', () => {
            window.location.href = `${JOB_URL_BASE}?id=${job.id}`;
        });
        tbody.appendChild(row);
    });

    renderPagination(result.count, page);
}

async function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete this job?')) return;

    const result = await apiFetch(`/jobs/${jobId}/`, { method: 'DELETE' });

    if (result === null || (result && result.error)) {
        alert('Failed to delete job');
        return;
    }

    loadHistory();
}

// Filter the rows on the current page by anything in the row's text.
const searchInput = document.getElementById('search-input');
if (searchInput) {
    searchInput.addEventListener('input', () => {
        const q = searchInput.value.trim().toLowerCase();
        document.querySelectorAll('#history-tbody tr').forEach((tr) => {
            tr.classList.toggle('hidden', q !== '' && !tr.textContent.toLowerCase().includes(q));
        });
    });
}

loadHistory();