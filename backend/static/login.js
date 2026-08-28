(() => {
    'use strict';
    const form = document.getElementById('login-form');
    const status = document.getElementById('login-status');
    const submit = form.querySelector('button[type="submit"]');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        submit.disabled = true;
        status.className = 'status';
        status.textContent = 'Signing in...';
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: form.username.value,
                    password: form.password.value,
                }),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail || 'Sign in failed');
            }
            window.location.assign('/admin');
        } catch (error) {
            status.className = 'status error';
            status.textContent = error.message;
            submit.disabled = false;
            form.password.select();
        }
    });
})();
