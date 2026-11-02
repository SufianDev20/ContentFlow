function showError(message) {
    const element = document.getElementById('form-error');
    element.textContent = message;
    element.classList.add('visible');
}

function clearError() {
    const element = document.getElementById('form-error');
    element.textContent = '';
    element.classList.remove('visible');
}

function setLoading(isLoading) {
    const button = document.getElementById('submit-btn');
    if (!button) return;

    button.disabled = isLoading;
    button.setAttribute('aria-busy', isLoading ? 'true' : 'false');
    button.textContent = isLoading ? 'Creating Account…' : 'Create account';
}

document.getElementById('register-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();

    const full_name = document.getElementById('full_name').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (!full_name) {
        showError('Enter your full name.');
        return;
    }
    if (!email.includes('@')) {
        showError('Enter a valid email address.');
        return;
    }

    setLoading(true);

    try {
        const response = await fetch(`${API_BASE_URL}/auth/register/`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ email, password, full_name })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            const message = data.detail || data.email?.[0] || data.password?.[0] || data.full_name?.[0] || 'Registration failed. Check your details and try again.';
            showError(message);
            setLoading(false);
            return;
        }

        window.location.href = `${LOGIN_URL}?registered=true`;
    } catch (err) {
        showError('Could not reach the server. Try again.');
        setLoading(false);
    }
});