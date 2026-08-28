(() => {
    'use strict';

    const form = document.getElementById('csv-import-form');
    const contractNo = document.getElementById('contract-no');
    const csvFile = document.getElementById('csv-file');
    const importButton = document.getElementById('btn-import');
    const status = document.getElementById('import-status');
    const user = document.getElementById('console-user');

    function setStatus(message, type = '') {
        status.textContent = message;
        status.className = `status${type ? ` ${type}` : ''}`;
    }

    async function readError(response, fallback) {
        const payload = await response.json().catch(() => ({}));
        if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg).join('; ');
        return payload.detail || fallback;
    }

    async function apiFetch(url, options = {}) {
        const response = await fetch(url, options);
        if (response.status === 401) window.location.assign('/login');
        return response;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const normalizedContractNo = contractNo.value.trim();
        const file = csvFile.files?.[0];
        if (!normalizedContractNo) {
            setStatus('Contract No. is required.', 'error');
            contractNo.focus();
            return;
        }
        if (!file) {
            setStatus('Choose a CSV file.', 'error');
            csvFile.focus();
            return;
        }
        if (!file.name.toLowerCase().endsWith('.csv') && !['text/csv', 'application/csv'].includes(file.type)) {
            setStatus('Only CSV files are accepted.', 'error');
            csvFile.focus();
            return;
        }

        const body = new FormData();
        body.append('contract_no', normalizedContractNo);
        body.append('file', file);
        importButton.disabled = true;
        setStatus('Importing…');
        try {
            const response = await apiFetch('/api/contract-services/import', { method: 'POST', body });
            if (!response.ok) throw new Error(await readError(response, 'Import failed'));
            const result = await response.json();
            setStatus(`${result.imported ?? 0} row${result.imported === 1 ? '' : 's'} imported.`, 'success');
            form.reset();
        } catch (error) {
            setStatus(error.message || 'Import failed', 'error');
        } finally {
            importButton.disabled = false;
        }
    });

    document.getElementById('btn-console-logout').addEventListener('click', async () => {
        await apiFetch('/api/auth/logout', { method: 'POST' });
        window.location.assign('/login');
    });

    (async () => {
        const response = await apiFetch('/api/auth/me');
        if (!response.ok) return;
        const identity = await response.json();
        if (!identity.is_admin) {
            window.location.assign('/');
            return;
        }
        user.textContent = identity.display_name || identity.username;
    })();
})();
