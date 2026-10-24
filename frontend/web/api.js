/**
 * api.js — real backend client.
 *
 * Authenticates against POST /api/v1/auth/token/ (username + password), stores
 * the DRF token in localStorage, and sends it as `Authorization: Token <key>`
 * on every request. Fact-checks are asynchronous: submit, then poll until the
 * run reaches a terminal status (ok | fallback | fail_state).
 */

const API_BASE = '/api/v1';
const TOKEN_KEY = 'fcai_token';

const TERMINAL_STATUSES = ['ok', 'fallback', 'fail_state'];

function token() {
    return localStorage.getItem(TOKEN_KEY);
}

function authHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const t = token();
    if (t) headers['Authorization'] = `Token ${t}`;
    return headers;
}

async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { ...(options.headers || {}), ...authHeaders() },
    });

    let data = null;
    const text = await response.text();
    if (text) {
        try { data = JSON.parse(text); } catch (_e) { data = text; }
    }

    if (response.status === 401 || response.status === 403) {
        throw new Error('Not authenticated. Please log in.');
    }
    if (!response.ok) {
        const detail = data && (data.detail || data.non_field_errors) || `Request failed (${response.status})`;
        throw new Error(Array.isArray(detail) ? detail.join(' ') : detail);
    }
    return data;
}

const Api = {
    isLoggedIn() {
        return Boolean(token());
    },

    async login(username, password) {
        try {
            const data = await request('/auth/token/', {
                method: 'POST',
                body: JSON.stringify({ username, password }),
            });
            localStorage.setItem(TOKEN_KEY, data.token);
            return { success: true, username };
        } catch (error) {
            return { success: false, message: error.message };
        }
    },

    logout() {
        localStorage.removeItem(TOKEN_KEY);
    },

    // Submit a claim (202), then poll until a terminal result is ready.
    async getCheckResult(claim) {
        const submitted = await request('/checks/', {
            method: 'POST',
            body: JSON.stringify({ claim }),
        });
        const checkId = submitted.check_id;

        for (let attempt = 0; attempt < 90; attempt++) {
            await new Promise((resolve) => setTimeout(resolve, 1000));
            const result = await request(`/checks/${checkId}/`);
            if (TERMINAL_STATUSES.includes(result.status)) {
                return result;
            }
        }
        throw new Error('Timed out waiting for a result.');
    },

    async getHistory() {
        const data = await request('/checks/');
        const rows = data.results || data;
        return rows.map((run) => ({
            id: run.check_id,
            claim: run.claim_text,
            verdict: run.verdict_enum || run.status,
            date: run.created_at ? new Date(run.created_at).toLocaleString() : '',
        }));
    },
};