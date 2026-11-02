// settings.js
// Handles the Account Settings modal on dashboard.html.
// Depends on API_BASE_URL, getCookie, csrfHeaders, apiFetch, handleAuthError from common.js
// FIXED: removed all localStorage.getItem('access_token') reads. Auth now
// rides on the httpOnly cookie via credentials: 'include'.

document.addEventListener('DOMContentLoaded', () => {
    const modalOverlay = document.getElementById('settings-modal-overlay');
    const modalClose = document.getElementById('settings-modal-close');
    const settingsTriggers = document.querySelectorAll('.settings-trigger');

    const errorEl = document.getElementById('settings-error');
    const successEl = document.getElementById('settings-success');

    const avatarInitial = document.getElementById('settings-avatar-initial');
    const avatarImg = document.getElementById('settings-avatar-img');
    const avatarInput = document.getElementById('settings-avatar-input');
    const avatarRemoveBtn = document.getElementById('settings-avatar-remove');

    const fullNameInput = document.getElementById('settings-full-name');
    const defaultModelSelect = document.getElementById('settings-default-model');
    const themeColorPicker = document.getElementById('settings-theme-color');
    const themeColorHex = document.getElementById('settings-theme-color-hex');
    const saveBtn = document.getElementById('settings-save-btn');

    const deleteAccountBtn = document.getElementById('settings-delete-account-btn');
    const deleteOverlay = document.getElementById('delete-confirm-overlay');
    const deleteClose = document.getElementById('delete-confirm-close');
    const deleteConfirmBtn = document.getElementById('delete-confirm-btn');
    const deletePasswordInput = document.getElementById('delete-confirm-password');
    const deleteErrorEl = document.getElementById('delete-confirm-error');

    if (!modalOverlay) return;

    let currentUser = null;
    let originalTheme = getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim();

    function showSettingsError(message) {
        errorEl.textContent = message;
        errorEl.classList.add('visible');
    }

    function clearSettingsError() {
        errorEl.textContent = '';
        errorEl.classList.remove('visible');
    }

    function showSettingsSuccess() {
        successEl.classList.remove('hidden');
        setTimeout(() => successEl.classList.add('hidden'), 2500);
    }

    function applyThemePreview(hex) {
        if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
            document.documentElement.style.setProperty('--color-primary', hex);
            document.documentElement.style.setProperty('--color-primary-container', hex);
        }
    }

    function updateAvatarDisplay(user) {
        const avatarUrl = user?.profile?.avatar_url;
        if (avatarUrl) {
            avatarImg.src = avatarUrl;
            avatarImg.classList.remove('hidden');
            avatarInitial.classList.add('hidden');
            avatarRemoveBtn.classList.remove('hidden');
        } else {
            avatarImg.classList.add('hidden');
            avatarInitial.classList.remove('hidden');
            avatarInitial.textContent = (user?.full_name || '?').trim().charAt(0).toUpperCase();
            avatarRemoveBtn.classList.add('hidden');
        }
    }

    // FIXED: was authHeaders() (undefined). Uses credentials: 'include'
    // so the httpOnly access-token cookie attaches automatically.
    async function populateModelOptions(selectedValue) {
        try {
            let response = await fetch(`${API_BASE_URL}/models/available/`, {
                credentials: 'include'
            });
            if (response.status === 401) {
                const refreshed = await handleAuthError();
                if (!refreshed) return;
                response = await fetch(`${API_BASE_URL}/models/available/`, {
                    credentials: 'include'
                });
            }
            if (!response.ok) return;

            const data = await response.json();
            const models = data.models || [];

            defaultModelSelect.innerHTML = '<option value="">No preference</option>';
            models.forEach((model) => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                defaultModelSelect.appendChild(option);
            });
            if (selectedValue) {
                defaultModelSelect.value = selectedValue;
            }
        } catch (err) {
            // Leave default option on failure
        }
    }

    async function loadSettings() {
        clearSettingsError();
        const result = await apiFetch('/auth/profile/', { method: 'GET' });
        if (!result || result.error) {
            showSettingsError(result?.error || 'Could not load settings.');
            return;
        }

        currentUser = result;
        fullNameInput.value = result.full_name || '';

        const theme = result.profile?.theme_color || '#8A2BE2';
        themeColorPicker.value = theme;
        themeColorHex.value = theme;

        updateAvatarDisplay(result);
        await populateModelOptions(result.profile?.default_model || '');
    }

    function openModal() {
        modalOverlay.classList.remove('hidden');
        loadSettings();
    }

    function closeModal() {
        modalOverlay.classList.add('hidden');
        clearSettingsError();
        if (currentUser?.profile?.theme_color) {
            applyThemePreview(currentUser.profile.theme_color);
        } else {
            document.documentElement.style.setProperty('--color-primary', originalTheme);
        }
    }

    settingsTriggers.forEach((trigger) => trigger.addEventListener('click', openModal));
    if (new URLSearchParams(window.location.search).get('setup') === 'default-model') {
        openModal();
    }
    if (modalClose) modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeModal();
    });

    // ---- Theme color sync ----
    themeColorPicker.addEventListener('input', () => {
        themeColorHex.value = themeColorPicker.value;
        applyThemePreview(themeColorPicker.value);
    });

    themeColorHex.addEventListener('input', () => {
        const value = themeColorHex.value.trim();
        if (/^#[0-9a-fA-F]{6}$/.test(value)) {
            themeColorPicker.value = value;
            applyThemePreview(value);
        }
    });

    // ---- Avatar upload with instant local preview ----
    // FIXED: was reading localStorage 'access_token' and sending
    // Authorization: Bearer null. Now sends the CSRF header only and
    // relies on the httpOnly cookie via credentials: 'include'.
    avatarInput.addEventListener('change', async () => {
        clearSettingsError();
        const file = avatarInput.files[0];
        if (!file) return;

        if (file.size > 2 * 1024 * 1024) {
            showSettingsError('Image must be under 2MB.');
            avatarInput.value = '';
            return;
        }

        // 1. Instant client-side preview
        const reader = new FileReader();
        reader.onload = (e) => {
            avatarImg.src = e.target.result;
            avatarImg.classList.remove('hidden');
            avatarInitial.classList.add('hidden');
        };
        reader.readAsDataURL(file);

        // 2. Upload to server
        const formData = new FormData();
        formData.append('avatar', file);

        const headers = csrfHeaders();

        try {
            let response = await fetch(`${API_BASE_URL}/auth/profile/avatar/`, {
                method: 'POST',
                credentials: 'include',
                headers,
                body: formData
            });

            if (response.status === 401) {
                const refreshed = await handleAuthError();
                if (!refreshed) return;
                response = await fetch(`${API_BASE_URL}/auth/profile/avatar/`, {
                    method: 'POST',
                    credentials: 'include',
                    headers,
                    body: formData
                });
            }

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                updateAvatarDisplay(currentUser);
                showSettingsError(data.avatar?.[0] || data.detail || 'Could not upload image.');
                return;
            }

            currentUser = data;
            updateAvatarDisplay(data);
            updateHeaderProfile(data.full_name || '', data.profile?.avatar_url || '');
            showSettingsSuccess();
        } catch (err) {
            updateAvatarDisplay(currentUser);
            showSettingsError('Could not reach the server. Try again.');
        } finally {
            avatarInput.value = '';
        }
    });

    avatarRemoveBtn.addEventListener('click', async () => {
        clearSettingsError();
        const result = await apiFetch('/auth/profile/avatar/', { method: 'DELETE' });
        if (!result || result.error) {
            showSettingsError(result?.error || 'Could not remove image.');
            return;
        }
        currentUser = result;
        updateAvatarDisplay(result);
        updateHeaderProfile(result.full_name || '', result.profile?.avatar_url || '');
        showSettingsSuccess();
    });

    // ---- Save profile settings ----
    saveBtn.addEventListener('click', async () => {
        clearSettingsError();

        const fullName = fullNameInput.value.trim();
        if (!fullName) {
            showSettingsError('Full name cannot be empty.');
            return;
        }

        const themeColor = themeColorHex.value.trim();
        if (!/^#[0-9a-fA-F]{6}$/.test(themeColor)) {
            showSettingsError('Enter a valid hex color, e.g. #8A2BE2.');
            return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';

        const result = await apiFetch('/auth/profile/', {
            method: 'PATCH',
            body: JSON.stringify({
                full_name: fullName,
                theme_color: themeColor,
                default_model: defaultModelSelect.value
            })
        });

        saveBtn.disabled = false;
        saveBtn.textContent = 'Save changes';

        if (!result || result.error) {
            showSettingsError(result?.error || 'Could not save settings.');
            return;
        }

        currentUser = result;
        updateAvatarDisplay(result);
        updateHeaderProfile(result.full_name || '', result.profile?.avatar_url || '');
        showSettingsSuccess();
    });

    // ---- Delete account flow ----
    function openDeleteModal() {
        deleteOverlay.classList.remove('hidden');
        deletePasswordInput.value = '';
        deleteErrorEl.textContent = '';
        deleteErrorEl.classList.remove('visible');
    }

    function closeDeleteModal() {
        deleteOverlay.classList.add('hidden');
    }

    if (deleteAccountBtn) deleteAccountBtn.addEventListener('click', openDeleteModal);
    if (deleteClose) deleteClose.addEventListener('click', closeDeleteModal);
    deleteOverlay.addEventListener('click', (e) => {
        if (e.target === deleteOverlay) closeDeleteModal();
    });

    // FIXED: was reading localStorage 'access_token' and sending
    // Authorization: Bearer '' when absent. Now uses apiFetch, which
    // sends the cookie and handles refresh/CSRF automatically.
    deleteConfirmBtn.addEventListener('click', async () => {
        const password = deletePasswordInput.value;
        if (!password) {
            deleteErrorEl.textContent = 'Enter your password.';
            deleteErrorEl.classList.add('visible');
            return;
        }

        deleteConfirmBtn.disabled = true;
        deleteConfirmBtn.textContent = 'Deleting…';

        const result = await apiFetch('/auth/account/', {
            method: 'DELETE',
            body: JSON.stringify({ password })
        });

        if (result === null) {
            // apiFetch already redirected to /login/ after a failed refresh
            return;
        }

        if (!result.error) {
            localStorage.removeItem('contentflow_draft');
            window.location.href = '/login/';
            return;
        }

        deleteErrorEl.textContent = result.error || 'Could not delete account.';
        deleteErrorEl.classList.add('visible');
        deleteConfirmBtn.disabled = false;
        deleteConfirmBtn.textContent = 'Permanently delete my account';
    });
});