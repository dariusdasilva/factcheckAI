const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

// Run the shipped classic script without exporting globals or contacting a server.
const source = readFileSync(join(__dirname, '..', 'api.js'), 'utf8');
function client(responses = []) {
    const values = new Map();
    const calls = [];
    const context = {
        localStorage: {
            getItem: key => values.get(key) || null,
            setItem: (key, value) => values.set(key, value),
            removeItem: key => values.delete(key),
        },
        setTimeout: callback => callback(),
        fetch: async (url, options) => {
            calls.push({ url, options });
            assert.ok(responses.length, `Unexpected request: ${url}`);
            const { status = 200, body = {} } = responses.shift();
            return { status, ok: status >= 200 && status < 300,
                text: async () => typeof body === 'string' ? body : JSON.stringify(body) };
        },
    };
    const api = runInNewContext(source + '\n;Api;', context);
    return { api, calls, values };
}

test('login stores a real backend token and logout removes it', async () => {
    const { api, calls, values } = client([{ body: { token: 'test-only-token' } }]);
    assert.equal(api.isLoggedIn(), false);
    assert.equal((await api.login('student', 'test-password')).success, true);
    assert.equal(values.get('fcai_token'), 'test-only-token');
    assert.equal(calls[0].url, '/api/v1/auth/token/');
    assert.equal(JSON.parse(calls[0].options.body).username, 'student');
    api.logout();
    assert.equal(api.isLoggedIn(), false);
});

test('failed login does not create a token', async () => {
    const { api } = client([{ status: 401, body: { detail: 'Invalid credentials' } }]);
    assert.equal((await api.login('student', 'wrong')).success, false);
    assert.equal(api.isLoggedIn(), false);
});

for (const status of ['ok', 'fallback', 'fail_state']) {
    test(`polls the returned check ID and preserves ${status}`, async () => {
        const result = { check_id: 42, status, verdict_enum: status === 'fail_state' ? null : 'unverified', confidence: null };
        const { api, calls, values } = client([
            { status: 202, body: { check_id: 42, status: 'queued' } },
            { body: { check_id: 42, status: 'running' } },
            { body: result },
        ]);
        values.set('fcai_token', 'test-only-token');
        const received = await api.getCheckResult('A claim requiring evidence');
        assert.equal(JSON.stringify(received), JSON.stringify(result));
        assert.equal(calls[0].options.headers.Authorization, 'Token test-only-token');
        assert.equal(calls[1].url, '/api/v1/checks/42/');
        assert.equal(calls.length, 3);
        if (status === 'fail_state') {
            assert.equal(received.verdict_enum, null);
            assert.equal(received.confidence, null);
        }
    });
}

test('submission errors do not become verdicts or trigger polling', async () => {
    const { api, calls } = client([{ status: 429, body: { detail: 'Quota exceeded' } }]);
    await assert.rejects(api.getCheckResult('A claim'), /Quota exceeded/);
    assert.equal(calls.length, 1);
});

test('history uses the authenticated paginated endpoint', async () => {
    const { api } = client([{ body: { count: 1, results: [
        { check_id: 7, claim_text: 'A saved claim', status: 'fail_state', verdict_enum: null },
    ] } }]);
    const history = await api.getHistory();
    assert.equal(history[0].id, 7);
    assert.equal(history[0].claim, 'A saved claim');
    assert.equal(history[0].verdict, 'fail_state');
});

test('exhausted polling rejects instead of fabricating a result', async () => {
    const { api, calls } = client([
        { status: 202, body: { check_id: 9 } },
        ...Array.from({ length: 90 }, () => ({ body: { status: 'running' } })),
    ]);
    await assert.rejects(api.getCheckResult('A slow claim'), /Timed out/);
    assert.equal(calls.length, 91);
});
