function showError(message) {
    const el = document.getElementById('form-error');
    el.textContent = message;
    el.classList.add('visible');
}

function setLoading(isLoading) {
    const btn = document.getElementById('submit-btn');
    btn.disabled = isLoading;
    btn.setAttribute('aria-busy', isLoading ? 'true' : 'false');
    btn.textContent = isLoading ? 'Signing in…' : 'Login';
}

const params = new URLSearchParams(window.location.search);
if (params.get('registered') === 'true') {
    document.getElementById('success-banner').classList.remove('hidden');
}

document.getElementById('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    document.getElementById('form-error').classList.remove('visible');

    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    setLoading(true);

    try {
        const response = await fetch(`${API_BASE_URL}/auth/login/`, {
            method: 'POST',
            credentials: 'include',  // NEW: lets the server set the httpOnly cookies
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ email, password })
        });

        if (!response.ok) {
            showError('Invalid email or password');
            setLoading(false);
            return;
        }

        // CHANGED: the response body no longer contains access/refresh
        // tokens, they are already set as cookies by the server. The body
        // now carries the non-sensitive fields login.js actually needs.
        const user = await response.json();

        window.location.href = user.default_model
            ? DASHBOARD_URL
            : `${DASHBOARD_URL}?setup=default-model`;
    }
    catch (err) {
        showError('Could not reach the server. Try Again.');
        setLoading(false);
    }
});