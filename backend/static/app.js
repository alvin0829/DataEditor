(() => {
    'use strict';

    const XXX_COLUMNS = [
        ['schedule_type', 'Schedule Type'], ['status', 'Status'], ['quotation_ref_no', 'Quotation Ref. No.'],
        ['quotation_date', 'Quotation Date'], ['quotation_amount', 'Quotation Amount'], ['emsd_group', 'EMSD Group'],
        ['department', 'Department'], ['venue', 'Venue'], ['description', 'Description'], ['remark', 'Remark'],
        ['po_no', 'P.O. no.'], ['po_date', 'P.O. Date'], ['po_amount', 'P.O. Amount'],
        ['invoice_no', 'Invoice No.'], ['invoice_date', 'Invoice Date'], ['invoice_amount', 'Invoice Amount'],
        ['emsd_assessed_amount', 'EMSD Assessed Amount'], ['payment', 'Payment'], ['payment_amount', 'Payment Amount'],
        ['rbq_no', 'RBQ No.'], ['rbq_venue', 'Venue', 'Venue (RBQ)'],
        ['repair_detail', '維修樓層 / 房號 / 故障詳情'], ['start_paper_date', '開工三色紙\n日期', '開工三色紙 日期'],
        ['start_paper', '開工三色紙'], ['finish_paper_date', '完工三色紙\n日期', '完工三色紙 日期'],
        ['finish_paper', '完工三色紙'], ['latest_status', '最新情況'], ['past_record', '過往紀錄'],
        ['emsd_person_in_charge', 'EMSD \nPerson In Charge', 'EMSD Person In Charge'],
        ['follow_up_personel', 'Follow Up Personel'], ['status_summary', 'Status\nSummary', 'Status Summary'],
        ['follow_up_date', 'Follow Up\nDate', 'Follow Up Date'], ['pc_remarks', 'PC\nRemarks', 'PC Remarks'],
        ['emsd_quotation_number', 'EMSD\n報價編號', 'EMSD 報價編號'], ['emsd_po_status', 'EMSD PO\nStatus', 'EMSD PO Status'],
        ['phase_1', 'Phase 1'], ['phase_2', 'Phase 2'], ['phase_3', 'Phase 3'], ['phase_4', 'Phase 4'],
        ['phase_5', 'Phase 5'], ['phase_6', 'Phase 6'], ['phase_7', 'Phase 7'], ['lock', '<- Lock'], ['pw', 'PW'],
    ].map(([key, label, apiKey]) => ({ key, label, apiKey: apiKey || label, width: label.length > 22 ? 240 : 155 }));

    const SHEETS = {
        xxx: {
            label: 'XXX Services',
            description: 'XXX!row 6 columns via /api/contract-services',
            listUrl: '/api/contract-services?limit=500',
            createUrl: '/api/contract-services',
            updateUrl: (id) => `/api/contract-services/${id}`,
            deleteUrl: (id) => `/api/contract-services/${id}`,
            canDelete: true,
            searchKeys: ['contract_no', ...XXX_COLUMNS.map((column) => column.key)],
            columns: [
                { key: 'contract_no', label: 'Contract No.', width: 160, required: true },
                ...XXX_COLUMNS,
            ],
            blank: () => Object.fromEntries([
                ['contract_no', ''],
                ...XXX_COLUMNS.map((column) => [column.key, '']),
            ]),
            fromApi: (item) => Object.fromEntries([
                ['contract_no', item.contract_no],
                ...XXX_COLUMNS.map((column) => [column.key, item.fields?.[column.apiKey] ?? '']),
            ]),
            toApi: (row) => ({
                contract_no: requiredText(row.contract_no, 'Contract No.'),
                fields: Object.fromEntries(XXX_COLUMNS.map((column) => [column.apiKey, row[column.key] ?? ''])),
            }),
        },
        settings: {
            label: 'User Settings',
            description: 'user_settings via /api/user-settings',
            listUrl: '/api/user-settings',
            createUrl: '/api/user-settings',
            updateUrl: (id) => `/api/user-settings/${id}`,
            deleteUrl: (id) => `/api/user-settings/${id}`,
            canDelete: true,
            searchKeys: ['email', 'display_name', 'role', 'theme', 'density', 'sidebar', 'notifications'],
            columns: [
                { key: 'email', label: 'Email', width: 220, type: 'email', required: true },
                { key: 'display_name', label: 'Display Name', width: 180, required: true },
                { key: 'role', label: 'Role', width: 110, options: ['user', 'admin', 'editor', 'viewer'] },
                { key: 'theme', label: 'Theme', width: 105, options: ['light', 'dark', 'auto'] },
                { key: 'density', label: 'Density', width: 125, options: ['default', 'compact', 'comfortable'] },
                { key: 'sidebar', label: 'Sidebar', width: 105, options: ['visible', 'hidden'] },
                { key: 'notifications', label: 'Notifications', width: 125, options: ['on', 'off'] },
                { key: 'active', label: 'Active', width: 80, type: 'boolean' },
                { key: 'updated_at', label: 'Updated At', width: 190, readonly: true },
            ],
            blank: () => ({
                email: '', display_name: '', role: 'user', theme: 'light', density: 'default',
                sidebar: 'visible', notifications: 'on', active: true, updated_at: '',
            }),
            fromApi: (item) => ({ ...item }),
            toApi: (row) => ({
                email: requiredText(row.email, 'Email'),
                display_name: requiredText(row.display_name, 'Display Name'),
                role: row.role,
                theme: row.theme,
                density: row.density,
                sidebar: row.sidebar,
                notifications: row.notifications,
                active: Boolean(row.active),
            }),
        },
    };

    const table = document.getElementById('spreadsheet');
    const tableHead = document.getElementById('table-head');
    const tableBody = document.getElementById('table-body');
    const emptyState = document.getElementById('empty-state');
    const searchInput = document.getElementById('search');
    const statusEl = document.getElementById('status');
    const formulaInput = document.getElementById('formula-input');
    const cellReference = document.getElementById('cell-reference');
    const sheetDescription = document.getElementById('sheet-description');
    const currentUser = document.getElementById('current-user');
    const adminConsoleLink = document.getElementById('admin-console-link');
    const btnAdd = document.getElementById('btn-add');
    const btnSave = document.getElementById('btn-save');
    const btnDelete = document.getElementById('btn-delete');
    const btnReload = document.getElementById('btn-reload');
    const btnLogout = document.getElementById('btn-logout');
    const confirmDialog = document.getElementById('confirm-dialog');
    const dialogMessage = document.getElementById('dialog-message');
    const dialogCancel = document.getElementById('dialog-cancel');
    const dialogConfirm = document.getElementById('dialog-confirm');

    let activeSheet = 'xxx';
    let rows = [];
    let selectedRow = -1;
    let selectedCol = -1;
    let confirmAction = null;

    function requiredText(value, label) {
        const text = String(value || '').trim();
        if (!text) throw new Error(`${label} is required`);
        return text;
    }

    function columnLetters(index) {
        let value = index + 1;
        let letters = '';
        while (value > 0) {
            value -= 1;
            letters = String.fromCharCode(65 + (value % 26)) + letters;
            value = Math.floor(value / 26);
        }
        return letters;
    }

    function config() { return SHEETS[activeSheet]; }

    async function apiFetch(url, options = {}) {
        const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (response.status === 401) {
            window.location.assign('/login');
            throw new Error('Authentication required');
        }
        return response;
    }

    async function readError(response, fallback) {
        const payload = await response.json().catch(() => ({}));
        if (Array.isArray(payload.detail)) {
            return payload.detail.map((item) => item.msg).join('; ');
        }
        return payload.detail || fallback;
    }

    function setStatus(message, type = '') {
        statusEl.textContent = message;
        statusEl.className = `status${type ? ` ${type}` : ''}`;
    }

    function dirtyCount() { return rows.filter((row) => row._dirty).length; }

    function updateActions() {
        const dirty = dirtyCount();
        btnSave.disabled = dirty === 0;
        btnDelete.disabled = selectedRow < 0 || !config().canDelete;
        btnDelete.title = config().canDelete ? 'Delete selected row' : 'Deletion is not exposed by this API';
        if (dirty) setStatus(`${dirty} unsaved row${dirty === 1 ? '' : 's'}`, 'dirty');
    }

    function filteredRows() {
        const query = searchInput.value.trim().toLowerCase();
        return rows.map((row, index) => ({ row, index })).filter(({ row }) => {
            if (!query) return true;
            return config().searchKeys.some((key) => String(row[key] ?? '').toLowerCase().includes(query));
        });
    }

    function createCellEditor(row, rowIndex, column, colIndex) {
        if (column.readonly) {
            const value = document.createElement('span');
            value.className = 'readonly';
            value.textContent = row[column.key] ? new Date(row[column.key]).toLocaleString() : '';
            value.title = value.textContent;
            value.tabIndex = 0;
            return value;
        }

        let editor;
        if (column.type === 'boolean') {
            editor = document.createElement('input');
            editor.type = 'checkbox';
            editor.checked = Boolean(row[column.key]);
            editor.addEventListener('change', () => setCellValue(rowIndex, colIndex, editor.checked));
        } else if (column.options) {
            editor = document.createElement('select');
            const options = column.options.includes(row[column.key])
                ? column.options
                : [row[column.key], ...column.options].filter(Boolean);
            options.forEach((optionValue) => {
                const option = document.createElement('option');
                option.value = optionValue;
                option.textContent = optionValue;
                editor.appendChild(option);
            });
            editor.value = row[column.key];
            editor.addEventListener('change', () => setCellValue(rowIndex, colIndex, editor.value));
        } else {
            editor = document.createElement('input');
            editor.type = column.type === 'email' ? 'email' : 'text';
            editor.value = row[column.key] ?? '';
            editor.addEventListener('input', () => setCellValue(rowIndex, colIndex, editor.value, false));
            editor.addEventListener('change', updateFormulaBar);
        }
        editor.setAttribute('aria-label', `${column.label}, row ${rowIndex + 1}`);
        editor.addEventListener('focus', () => selectCell(rowIndex, colIndex, false));
        editor.addEventListener('click', () => selectCell(rowIndex, colIndex, false));
        return editor;
    }

    function render() {
        const currentConfig = config();
        table.setAttribute('aria-label', `${currentConfig.label} database records`);
        sheetDescription.textContent = currentConfig.description;

        const headerRow = document.createElement('tr');
        const corner = document.createElement('th');
        corner.className = 'row-number';
        corner.scope = 'col';
        corner.textContent = '#';
        headerRow.appendChild(corner);
        currentConfig.columns.forEach((column) => {
            const th = document.createElement('th');
            th.scope = 'col';
            th.style.width = `${column.width}px`;
            th.style.minWidth = `${column.width}px`;
            th.textContent = column.label;
            headerRow.appendChild(th);
        });
        tableHead.replaceChildren(headerRow);
        tableBody.replaceChildren();

        const visibleRows = filteredRows();
        visibleRows.forEach(({ row, index }) => {
            const tr = document.createElement('tr');
            tr.dataset.row = index;
            if (index === selectedRow) tr.classList.add('row-selected');
            if (row._dirty) tr.classList.add('dirty');
            if (row._error) tr.classList.add('error');

            const rowNumber = document.createElement('td');
            rowNumber.className = 'row-number';
            const rowButton = document.createElement('button');
            rowButton.type = 'button';
            rowButton.textContent = String(index + 1);
            rowButton.setAttribute('aria-label', `Select row ${index + 1}`);
            rowButton.addEventListener('click', () => selectCell(index, -1));
            rowNumber.appendChild(rowButton);
            tr.appendChild(rowNumber);

            currentConfig.columns.forEach((column, colIndex) => {
                const td = document.createElement('td');
                td.className = 'cell';
                td.dataset.row = index;
                td.dataset.col = colIndex;
                td.style.width = `${column.width}px`;
                td.style.minWidth = `${column.width}px`;
                if (index === selectedRow && colIndex === selectedCol) td.classList.add('selected');
                td.appendChild(createCellEditor(row, index, column, colIndex));
                td.addEventListener('mousedown', () => selectCell(index, colIndex, false));
                tr.appendChild(td);
            });
            tableBody.appendChild(tr);
        });

        emptyState.hidden = visibleRows.length !== 0;
        document.querySelectorAll('[data-sheet]').forEach((tab) => {
            tab.setAttribute('aria-selected', String(tab.dataset.sheet === activeSheet));
        });
        updateFormulaBar();
        updateActions();
    }

    function selectCell(rowIndex, colIndex, shouldRender = true) {
        selectedRow = rowIndex;
        selectedCol = colIndex;
        if (shouldRender) render();
        else {
            document.querySelectorAll('td.cell.selected').forEach((cell) => cell.classList.remove('selected'));
            document.querySelector(`td.cell[data-row="${rowIndex}"][data-col="${colIndex}"]`)?.classList.add('selected');
            updateFormulaBar();
            updateActions();
        }
    }

    function updateFormulaBar() {
        const column = config().columns[selectedCol];
        const row = rows[selectedRow];
        if (!row || !column) {
            cellReference.textContent = selectedRow >= 0 ? String(selectedRow + 1) : '—';
            formulaInput.value = '';
            formulaInput.disabled = true;
            return;
        }
        cellReference.textContent = `${columnLetters(selectedCol)}${selectedRow + 1}`;
        formulaInput.value = String(row[column.key] ?? '');
        formulaInput.disabled = column.readonly || column.type === 'boolean';
    }

    function setCellValue(rowIndex, colIndex, value, rerender = true) {
        const row = rows[rowIndex];
        const column = config().columns[colIndex];
        if (!row || !column || column.readonly) return;
        row[column.key] = value;
        row._dirty = true;
        row._error = '';
        selectedRow = rowIndex;
        selectedCol = colIndex;
        if (rerender) render();
        else updateActions();
    }

    async function loadSheet() {
        setStatus('Loading…');
        const currentConfig = config();
        try {
            const response = await apiFetch(currentConfig.listUrl);
            if (!response.ok) throw new Error(await readError(response, 'Load failed'));
            const payload = await response.json();
            rows = (payload.items || []).map((item) => ({
                ...currentConfig.fromApi(item),
                _serverId: item.id,
                _new: false,
                _dirty: false,
                _error: '',
            }));
            selectedRow = -1;
            selectedCol = -1;
            searchInput.value = '';
            render();
            setStatus(`${rows.length} row${rows.length === 1 ? '' : 's'} loaded`, 'success');
        } catch (error) {
            rows = [];
            render();
            setStatus(error.message || 'Load failed', 'error');
        }
    }

    async function saveRows() {
        const currentConfig = config();
        const dirtyRows = rows.filter((row) => row._dirty);
        if (!dirtyRows.length) return;
        setStatus(`Saving ${dirtyRows.length} row${dirtyRows.length === 1 ? '' : 's'}…`);
        let failures = 0;

        for (const row of dirtyRows) {
            try {
                const body = currentConfig.toApi(row);
                const isNew = row._new;
                const response = await apiFetch(
                    isNew ? currentConfig.createUrl : currentConfig.updateUrl(row._serverId),
                    { method: isNew ? 'POST' : 'PATCH', body: JSON.stringify(body) },
                );
                if (!response.ok) throw new Error(await readError(response, 'Save failed'));
                const saved = await response.json();
                Object.assign(row, currentConfig.fromApi(saved), {
                    _serverId: saved.id,
                    _new: false,
                    _dirty: false,
                    _error: '',
                });
            } catch (error) {
                row._error = error.message || 'Save failed';
                failures += 1;
            }
        }
        render();
        if (failures) setStatus(`${failures} row${failures === 1 ? '' : 's'} failed to save`, 'error');
        else setStatus('All changes saved', 'success');
    }

    function addRow() {
        const row = {
            ...config().blank(),
            _serverId: null,
            _new: true,
            _dirty: true,
            _error: '',
        };
        rows.unshift(row);
        selectedRow = 0;
        selectedCol = 0;
        render();
        focusCell(0, 0);
    }

    function showConfirm(message, action) {
        dialogMessage.textContent = message;
        confirmAction = action;
        confirmDialog.hidden = false;
        dialogConfirm.focus();
    }

    function closeConfirm() {
        confirmDialog.hidden = true;
        confirmAction = null;
        btnDelete.focus();
    }

    async function deleteSelected() {
        if (selectedRow < 0 || !config().canDelete) return;
        const row = rows[selectedRow];
        if (row._new) {
            rows.splice(selectedRow, 1);
            selectedRow = -1;
            selectedCol = -1;
            render();
            setStatus('Unsaved row removed', 'success');
            return;
        }
        const response = await apiFetch(config().deleteUrl(row._serverId), { method: 'DELETE' });
        if (!response.ok) {
            setStatus(await readError(response, 'Delete failed'), 'error');
            return;
        }
        rows.splice(selectedRow, 1);
        selectedRow = -1;
        selectedCol = -1;
        render();
        setStatus('Row deleted', 'success');
    }

    function focusCell(rowIndex, colIndex) {
        const selector = `td.cell[data-row="${rowIndex}"][data-col="${colIndex}"] input, td.cell[data-row="${rowIndex}"][data-col="${colIndex}"] select, td.cell[data-row="${rowIndex}"][data-col="${colIndex}"] .readonly`;
        document.querySelector(selector)?.focus();
    }

    function moveSelection(rowDelta, colDelta) {
        if (!rows.length) return;
        const nextRow = Math.max(0, Math.min(rows.length - 1, selectedRow + rowDelta));
        const nextCol = Math.max(0, Math.min(config().columns.length - 1, Math.max(0, selectedCol) + colDelta));
        selectedRow = nextRow;
        selectedCol = nextCol;
        render();
        focusCell(nextRow, nextCol);
    }

    function handleGridKeys(event) {
        if (!event.target.closest('#spreadsheet') || selectedRow < 0) return;
        if (event.key === 'Enter') {
            event.preventDefault();
            moveSelection(event.shiftKey ? -1 : 1, 0);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            selectedRow = -1;
            selectedCol = -1;
            render();
        }
    }

    async function switchSheet(sheetName) {
        if (sheetName === activeSheet) return;
        if (dirtyCount()) {
            setStatus('Save or reload changes before switching sheets', 'error');
            return;
        }
        activeSheet = sheetName;
        await loadSheet();
    }

    formulaInput.addEventListener('input', () => {
        if (selectedRow < 0 || selectedCol < 0) return;
        setCellValue(selectedRow, selectedCol, formulaInput.value, false);
        const editor = document.querySelector(`td.cell[data-row="${selectedRow}"][data-col="${selectedCol}"] input[type="text"], td.cell[data-row="${selectedRow}"][data-col="${selectedCol}"] input[type="email"]`);
        if (editor) editor.value = formulaInput.value;
    });

    btnAdd.addEventListener('click', addRow);
    btnSave.addEventListener('click', saveRows);
    btnReload.addEventListener('click', loadSheet);
    btnDelete.addEventListener('click', () => {
        const row = rows[selectedRow];
        if (!row) return;
        if (row._new) deleteSelected();
        else showConfirm(`Delete ${row.contract_no || row.email || `row ${selectedRow + 1}`}?`, deleteSelected);
    });
    searchInput.addEventListener('input', render);
    table.addEventListener('keydown', handleGridKeys);
    document.querySelectorAll('[data-sheet]').forEach((tab) => {
        tab.addEventListener('click', () => switchSheet(tab.dataset.sheet));
    });
    dialogCancel.addEventListener('click', closeConfirm);
    dialogConfirm.addEventListener('click', async () => {
        const action = confirmAction;
        confirmDialog.hidden = true;
        confirmAction = null;
        if (action) await action();
    });
    confirmDialog.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeConfirm();
        if (event.key === 'Tab') {
            const target = event.shiftKey ? dialogCancel : dialogConfirm;
            if (document.activeElement !== target) {
                event.preventDefault();
                target.focus();
            }
        }
    });
    btnLogout.addEventListener('click', async () => {
        await apiFetch('/api/auth/logout', { method: 'POST' });
        window.location.assign('/login');
    });

    (async () => {
        let editableSheets = null;
        try {
            const response = await apiFetch('/api/auth/me');
            if (!response.ok) {
                // FIX 6: Do not expose tabs or load data if identity fetch fails.
                document.querySelectorAll('[data-sheet]').forEach((tab) => { tab.hidden = true; });
                setStatus('Access denied. Please sign in with an authorized account.', 'error');
                return;
            }
            const identity = await response.json();
            currentUser.textContent = identity.display_name || identity.username;
            adminConsoleLink.hidden = !identity.is_admin;
            editableSheets = identity.editable_sheets || [];
        } catch (_error) {
            document.querySelectorAll('[data-sheet]').forEach((tab) => { tab.hidden = true; });
            setStatus('Unable to verify access. Please sign in again.', 'error');
            return;
        }
        // Filter sheet tabs to only show permitted sheets.
        const sheetTabs = document.querySelectorAll('[data-sheet]');
        let firstVisible = null;
        sheetTabs.forEach((tab) => {
            const key = tab.dataset.sheet;
            const allowed = editableSheets.includes(key);
            tab.hidden = !allowed;
            if (!allowed && tab.getAttribute('aria-selected') === 'true') {
                tab.setAttribute('aria-selected', 'false');
            }
            if (allowed && !firstVisible) firstVisible = key;
        });
        // FIX 6: Do not call loadSheet when firstVisible is null.
        if (!firstVisible) {
            setStatus('No permitted sheets. Contact your administrator.', 'error');
            return;
        }
        // Switch to first visible sheet if current selection is hidden.
        if (activeSheet !== firstVisible) {
            const currentTab = document.querySelector(`[data-sheet="${activeSheet}"]`);
            if (!currentTab || currentTab.hidden) {
                activeSheet = firstVisible;
                const targetTab = document.querySelector(`[data-sheet="${firstVisible}"]`);
                if (targetTab) targetTab.setAttribute('aria-selected', 'true');
            }
        }
        await loadSheet();
    })();
})();


