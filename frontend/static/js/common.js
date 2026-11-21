const API_BASE_URL = '/api/v1';

function getCookie(name) {
    const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? decodeURIComponent(match[2]) : null;
}

// The JWT lives in httpOnly cookies; JS only supplies the CSRF header.
function csrfHeaders() {
    return { 'X-CSRFToken': getCookie('csrftoken') };
}

async function refreshAccessToken() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeaders()
            }
        });
        return response.ok;
    } catch (err) {
        console.error('Token refresh failed:', err);
        return false;
    }
}

async function handleAuthError() {
    const refreshSuccess = await refreshAccessToken();
    if (refreshSuccess) {
        return true;
    } else {
        await fetch(`${API_BASE_URL}/auth/logout/`, {
            method: 'POST',
            credentials: 'include',
            headers: csrfHeaders()
        }).catch(() => { });
        window.location.href = '/login/';
        return false;
    }
}

// Turns DRF field errors ({"field": ["msg"], "list": {"0": ["msg"]}}) into one readable line.
function flattenFieldErrors(data, prefix = '') {
    if (!data || typeof data !== 'object') return '';
    const parts = [];
    for (const [key, value] of Object.entries(data)) {
        const label = /^\d+$/.test(key) ? `${prefix} #${Number(key) + 1}` : key.replace(/_/g, ' ');
        if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
            parts.push(`${label}: ${value.join(' ')}`);
        } else if (typeof value === 'string') {
            parts.push(`${label}: ${value}`);
        } else {
            parts.push(flattenFieldErrors(value, label));
        }
    }
    return parts.filter(Boolean).join(' · ');
}

function sendRequest(path, options) {
    const headers = { ...csrfHeaders(), ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    return fetch(`${API_BASE_URL}${path}`, { ...options, credentials: 'include', headers });
}

// Resolves to the parsed JSON body, `{ error }` on failure, or null when the
// session is gone (after redirecting to login). Retries once after a token refresh.
async function apiFetch(path, options = {}) {
    let response = await sendRequest(path, options);

    if (response.status === 401) {
        if (!(await handleAuthError())) return null;
        response = await sendRequest(path, options);
    }

    if (response.status === 429) {
        return { error: 'Too many requests. Please wait a moment.' };
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        return { error: data.detail || data.error || flattenFieldErrors(data) || 'Request failed.' };
    }
    return data;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function formatDate(iso) {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatDateTime(iso) {
    return new Date(iso).toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
    });
}

const STAR_PATH = 'M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8z';

function renderRatingWidget(outputId, currentRating) {
    let stars = '';
    for (let i = 1; i <= 5; i++) {
        const filled = currentRating && i <= currentRating ? 'filled' : '';
        stars += `<span class="star ${filled}" data-output-id="${outputId}" data-value="${i}" role="button" aria-label="Rate ${i} of 5"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${STAR_PATH}"/></svg></span>`;
    }
    return `<div class="rating-widget">${stars}</div>`;
}

function bindCopyButton(card) {
    const button = card.querySelector('.copy-btn');
    button.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(button.dataset.text);
            button.textContent = 'Copied!';
        } catch (err) {
            button.textContent = 'Copy failed';
        }
        setTimeout(() => { button.textContent = 'Copy'; }, 1500);
    });
}

// One output as a card: text, metrics and rating, plus optional extra markup at the bottom.
function renderOutputCard(output, extrasHtml = '') {
    const card = document.createElement('div');
    card.className = 'output-card';
    card.innerHTML = `
    <div class="output-card-header">
      <span class="output-card-format">${escapeHtml(output.format.replace('_', ' '))}</span>
      <button class="copy-btn" data-text="${escapeHtml(output.text)}">Copy</button>
    </div>
    <p class="output-card-body">${escapeHtml(output.text)}</p>
    <div class="output-metrics-display">
      <div class="output-metric-item">
        <span class="output-metric-label">Quality</span>
        <span class="output-metric-value">${(output.quality_score / 10).toFixed(1)}</span>
      </div>
      <div class="output-metric-item">
        <span class="output-metric-label">Tokens</span>
        <span class="output-metric-value">${output.tokens_generated}</span>
      </div>
      <div class="output-metric-item">
        <span class="output-metric-label">Latency</span>
        <span class="output-metric-value">${output.latency_ms}ms</span>
      </div>
      <div class="output-metric-item">
        <span class="output-metric-label">Speed</span>
        <span class="output-metric-value">${output.tokens_per_second} t/s</span>
      </div>
    </div>
    ${renderRatingWidget(output.id, output.user_rating)}
    ${extrasHtml}
  `;
    bindCopyButton(card);
    return card;
}

function showFormError(message) {
    const el = document.getElementById('form-error');
    el.textContent = message;
    el.classList.add('visible');
}

function clearFormError() {
    const el = document.getElementById('form-error');
    el.textContent = '';
    el.classList.remove('visible');
}

document.addEventListener('click', async (e) => {
    const star = e.target.closest('.star');
    if (!star) return;
    const rating = parseInt(star.dataset.value, 10);

    const saved = await apiFetch(`/outputs/${star.dataset.outputId}/rate/`, {
        method: 'PATCH',
        body: JSON.stringify({ user_rating: rating })
    });
    if (!saved || saved.error) return;

    star.closest('.rating-widget').querySelectorAll('.star').forEach((s) => {
        s.classList.toggle('filled', parseInt(s.dataset.value, 10) <= rating);
    });
});

// Fills a <select> with the models the server offers, grouped by provider.
// Resolves to false if they could not be loaded.
async function populateModelSelect(select) {
    const data = await apiFetch('/models/available/');
    if (!data || data.error) return false;

    const groups = [['OpenRouter', data.openrouter], ['Gemini', data.gemini]];
    for (const [label, models] of groups) {
        if (!models?.length) continue;
        const group = document.createElement('optgroup');
        group.label = label;
        for (const model of models) group.appendChild(new Option(model, model));
        select.appendChild(group);
    }
    return true;
}

async function loadAvailableModels() {
    const select = document.getElementById('model-select');
    select.innerHTML = '';
    if (!(await populateModelSelect(select))) {
        select.innerHTML = '<option value="" disabled>Could not load models</option>';
    } else if (!select.children.length) {
        select.innerHTML = '<option value="" disabled>No models available</option>';
    }
}

function initSidebarToggle() {
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const mainContent = document.querySelector('.main-with-sidebar');

    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileDrawer = document.getElementById('mobile-drawer');
    const mobileDrawerToggle = document.getElementById('mobile-drawer-toggle');
    const mobileDrawerOverlay = document.getElementById('mobile-drawer-overlay');
    const sidebarReopen = document.getElementById('sidebar-reopen');

    if (sidebarReopen && sidebar) {
        sidebarReopen.addEventListener('click', () => {
            sidebar.classList.remove('collapsed');
            if (mainContent) mainContent.classList.remove('expanded');
        });
    }

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            if (mainContent) {
                mainContent.classList.toggle('expanded');
            }
        });
    }

    if (sidebarOverlay && sidebar) {
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.add('collapsed');
            if (mainContent) {
                mainContent.classList.add('expanded');
            }
            sidebarOverlay.classList.remove('open');
        });
    }

    function openDrawer() {
        if (mobileDrawer) mobileDrawer.classList.add('open');
        if (mobileDrawerOverlay) mobileDrawerOverlay.classList.add('open');
    }

    function closeDrawer() {
        if (mobileDrawer) mobileDrawer.classList.remove('open');
        if (mobileDrawerOverlay) mobileDrawerOverlay.classList.remove('open');
    }

    if (mobileMenuToggle) mobileMenuToggle.addEventListener('click', openDrawer);
    if (mobileDrawerToggle) mobileDrawerToggle.addEventListener('click', closeDrawer);
    if (mobileDrawerOverlay) mobileDrawerOverlay.addEventListener('click', closeDrawer);
}

function applyTheme(theme) {
    const themeValue = theme === 'light' ? 'light' : 'dark';
    const changed = document.documentElement.getAttribute('data-theme') !== themeValue;
    document.documentElement.setAttribute('data-theme', themeValue);
    document.body.setAttribute('data-theme', themeValue);
    localStorage.setItem('theme_preference', themeValue);
    document.querySelectorAll('.theme-toggle-label').forEach((el) => {
        el.textContent = themeValue === 'light' ? 'Dark theme' : 'Light theme';
    });
    if (changed) document.dispatchEvent(new CustomEvent('themechange', { detail: themeValue }));
}

function initLogout() {
    document.querySelectorAll('a[href="/logout/"]').forEach((link) => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            await sendRequest('/auth/logout/', { method: 'POST' }).catch(() => { });
            window.location.href = '/login/';
        });
    });
}

function initThemeToggle() {
    document.querySelectorAll('.theme-toggle').forEach((btn) => {
        btn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            applyTheme(current === 'light' ? 'dark' : 'light');
        });
    });
}

function updateHeaderProfile(displayName = '', imageUrl = '') {
    const initial = (displayName || '?').trim().charAt(0).toUpperCase();

    document.querySelectorAll('.nav-avatar-preview').forEach((preview) => {
        const initialEl = preview.querySelector('.nav-avatar-initial');
        const imgEl = preview.querySelector('.nav-avatar-img');

        if (imageUrl) {
            if (imgEl) {
                imgEl.src = imageUrl;
                imgEl.classList.remove('hidden');
            }
            if (initialEl) initialEl.classList.add('hidden');
        } else {
            if (imgEl) imgEl.classList.add('hidden');
            if (initialEl) {
                initialEl.textContent = initial;
                initialEl.classList.remove('hidden');
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    initSidebarToggle();
    initThemeToggle();
    initLogout();
    applyTheme(localStorage.getItem('theme_preference') || 'dark');

    if (document.getElementById('model-select')) loadAvailableModels();

    // The httpOnly token is invisible to JS, so the page declares auth state itself.
    if (!window.authenticated) return;

    const me = await apiFetch('/auth/me/');
    if (me && !me.error) {
        updateHeaderProfile(me.full_name || 'Profile', me.profile?.avatar_url || '');
    }
});
