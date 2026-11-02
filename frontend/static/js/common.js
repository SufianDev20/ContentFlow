// This folder contains all the common functions in all of the javascript
const API_BASE_URL = '/api/v1';

function getCookie(name) {
    const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? decodeURIComponent(match[2]) : null;
}

// CHANGED: no more reading access_token from localStorage. The JWT cookie
// is httpOnly, so JS cannot see it and doesn't need to. Only the CSRF
// header is set manually now.
function csrfHeaders() {
    return { 'X-CSRFToken': getCookie('csrftoken') };
}

// CHANGED: refresh no longer takes a token argument or touches localStorage.
// The refresh cookie is sent automatically because of credentials: 'include'.
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
        // CHANGED: nothing to clear from localStorage anymore. Ask the
        // server to drop the cookies, then redirect.
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

// Export a common API fetch function that can be used by other files
async function apiFetch(path, options = {}) {
    let response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        credentials: 'include',  // NEW: sends the httpOnly JWT cookie automatically
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeaders(),
            ...(options.headers || {})
        }
    });

    if (response.status === 401) {
        const refreshSuccess = await handleAuthError();
        if (refreshSuccess) {
            response = await fetch(`${API_BASE_URL}${path}`, {
                ...options,
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    ...csrfHeaders(),
                    ...(options.headers || {})
                }
            });
        } else {
            return null;
        }
    }

    if (response.status === 429) {
        console.warn('Rate limit hit (429). Throttling request.');
        return { error: 'Too many requests. Please wait a moment.' };
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        return { error: data.detail || data.error || flattenFieldErrors(data) || 'Request failed.' };
    }
    return data;
}

async function loadAvailableModels() {
    const modelSelect = document.getElementById('model-select');
    if (!modelSelect) return;

    try {
        let response = await fetch(`${API_BASE_URL}/models/available/`, {
            credentials: 'include'
        });

        if (response.status === 401) {
            const refreshSuccess = await handleAuthError();
            if (refreshSuccess) {
                response = await fetch(`${API_BASE_URL}/models/available/`, {
                    credentials: 'include'
                });
            } else {
                return;
            }
        }

        if (!response.ok) {
            modelSelect.innerHTML = '<option value="" disabled>Could not load models</option>';
            return;
        }

        const data = await response.json();
        const models = data.models || [];

        const openrouterModels = models.filter(m => !m.startsWith('gemini-'));
        const geminiModels = models.filter(m => m.startsWith('gemini-'));

        modelSelect.innerHTML = '';

        if (openrouterModels.length > 0) {
            const openrouterGroup = document.createElement('optgroup');
            openrouterGroup.label = 'OpenRouter';
            openrouterModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                openrouterGroup.appendChild(option);
            });
            modelSelect.appendChild(openrouterGroup);
        }

        if (geminiModels.length > 0) {
            const geminiGroup = document.createElement('optgroup');
            geminiGroup.label = 'Gemini';
            geminiModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                geminiGroup.appendChild(option);
            });
            modelSelect.appendChild(geminiGroup);
        }

        if (models.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No models available';
            option.disabled = true;
            modelSelect.appendChild(option);
        }
    } catch (err) {
        modelSelect.innerHTML = '<option value="" disabled>Could not load models</option>';
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

// Single consolidated DOM initialization handler
document.addEventListener('DOMContentLoaded', async () => {
    if (document.getElementById('model-select')) {
        loadAvailableModels();
    }

    initSidebarToggle();
    initThemeToggle();
    applyTheme(localStorage.getItem('theme_preference') || 'dark');

    // CHANGED: we can no longer check `localStorage.getItem('access_token')`
    // to know if the user is logged in, since the token is httpOnly and
    // invisible to JS. window.authenticated is set server-side in
    // dashboard.html's extra_head block; use that instead, and otherwise
    // just attempt the request and let the 401 path handle it.
    if (!window.authenticated) {
        applyTheme(localStorage.getItem('theme_preference') || 'dark');
        return;
    }

    try {
        const response = await apiFetch('/auth/me/');
        if (response && !response.error) {
            applyTheme(localStorage.getItem('theme_preference') || response.theme_preference || 'dark');
            const displayName = response.display_name || response.full_name || 'Profile';
            const avatarUrl = response.profile?.avatar_url || '';
            updateHeaderProfile(displayName, avatarUrl);
        } else {
            applyTheme(localStorage.getItem('theme_preference') || 'dark');
        }
    } catch (err) {
        console.error('Failed to initialize user session state:', err);
        applyTheme(localStorage.getItem('theme_preference') || 'dark');
    }
});