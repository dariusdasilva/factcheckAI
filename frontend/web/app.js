/**
 * app.js — The "Manager"
 * This file handles the UI logic: clicking buttons, swapping screens, 
 * and updating the text on the page.
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log("[App] Initializing FactCheckAI Web App...");

    // --- Model Data (from ARCHITECTURE.md §3.1) ---
    const GEMMA_MODELS = {
        api: [
            { id: 'google/gemma-4-26b-a4b-it:free', name: 'Gemma 4 26B (Free)', cost: 0 },
            { id: 'google/gemma-4-26b-a4b-it', name: 'Gemma 4 26B (Paid)', cost: 0.00032 },
            { id: 'google/gemma-4-31b-it:free', name: 'Gemma 4 31B (Free)', cost: 0 },
            { id: 'google/gemma-4-31b-it', name: 'Gemma 4 31B (Paid)', cost: 0.00081 },
            { id: 'google/gemma-3-12b-it', name: 'Gemma 3 12B', cost: 0.00023 },
        ],
        local: [
            { id: 'gemma4:e4b-it-qat', name: 'Gemma 4 e4b (QAT)' },
            { id: 'gemma4:e2b-it-qat', name: 'Gemma 4 e2b (Low-Res)' },
        ]
    };

    // --- 1. Elements ---
    const screens = {
        login: document.getElementById('screen-login'),
        register: document.getElementById('screen-register'),
        submit: document.getElementById('screen-submit'),
        result: document.getElementById('screen-result'),
        history: document.getElementById('screen-history'),
        settings: document.getElementById('screen-settings'),
    };

    const navLinks = document.getElementById('nav-links');

    // --- 2. Navigation Logic ---
    function showScreen(screenName) {
        console.log(`[App] Switching to screen: ${screenName}`);
        Object.values(screens).forEach(s => s.classList.add('hidden'));
        screens[screenName].classList.remove('hidden');
    }

    // --- 3. Auth Flow ---
    document.getElementById('link-to-register').addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('register');
    });

    document.getElementById('link-to-login').addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('login');
    });

    document.getElementById('nav-settings').addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('settings');
        populateModels(); // Refresh models when entering settings
    });

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const user = document.getElementById('username').value;
        const pass = document.getElementById('password').value;

        const response = await Api.login(user, pass);
        if (response.success) {
            console.log("[App] Login successful!");
            navLinks.classList.remove('hidden');
            showScreen('submit');
        } else {
            alert(response.message);
        }
    });

    document.getElementById('register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const user = document.getElementById('reg-username').value;
        const email = document.getElementById('reg-email').value;
        const pass = document.getElementById('reg-password').value;

        const response = await Api.register(user, email, pass);
        if (response.success) {
            alert(response.message);
            showScreen('login');
        }
    });

    document.getElementById('nav-logout').addEventListener('click', (e) => {
        e.preventDefault();
        navLinks.classList.add('hidden');
        showScreen('login');
    });

    // --- 4. Fact Check Flow ---
    document.getElementById('submit-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const claim = document.getElementById('claim-text').value;
        showScreen('result');
        document.getElementById('result-verdict').innerText = "Analyzing claim...";
        document.getElementById('result-detail').innerText = "Our AI is searching for evidence...";
        document.getElementById('result-evidence').innerHTML = "";
        document.getElementById('result-banner').classList.add('hidden');

        const result = await Api.getCheckResult(claim);
        renderResult(result);
    });

    function renderResult(data) {
        const verdictEl = document.getElementById('result-verdict');
        const confEl = document.getElementById('result-confidence');
        const detailEl = document.getElementById('result-detail');
        const evidenceEl = document.getElementById('result-evidence');
        const bannerEl = document.getElementById('result-banner');

        bannerEl.classList.add('hidden');
        bannerEl.className = 'banner';

        if (data.status === 'fail_state') {
            bannerEl.innerText = data.detail;
            bannerEl.classList.add('banner-fail');
            bannerEl.classList.remove('hidden');
            verdictEl.innerText = "Service Unavailable";
            confEl.innerText = "N/A";
            detailEl.innerText = "We couldn't reach our AI providers. Please try again later.";
            evidenceEl.innerHTML = "";
            return;
        }

        if (data.status === 'fallback') {
            bannerEl.innerText = "Running in Local Mode: Cloud AI is currently offline.";
            bannerEl.classList.add('banner-local');
            bannerEl.classList.remove('hidden');
        }

        verdictEl.innerText = `Verdict: ${data.verdict.toUpperCase()}`;
        confEl.innerText = `${(data.confidence * 100).toFixed(0)}% Confidence`;
        detailEl.innerText = data.detail;

        evidenceEl.innerHTML = data.evidence.map(ev => `
            <li>
                <strong>${ev.id}</strong>: ${ev.snippet}<br>
                <small><a href="${ev.url}" target="_blank">${ev.url}</a></small>
            </li>
        `).join('');
    }

    document.getElementById('btn-back-submit').addEventListener('click', () => {
        showScreen('submit');
    });

    // --- 5. History Flow ---
    document.getElementById('nav-history').addEventListener('click', async (e) => {
        e.preventDefault();
        showScreen('history');
        const history = await Api.getHistory();
        const listEl = document.getElementById('history-list');
        listEl.innerHTML = history.map(item => `
            <div class="card" style="margin-bottom: 1rem; padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>${item.claim}</strong><br>
                    <small>${item.date}</small>
                </div>
                <span class="badge">${item.verdict}</span>
            </div>
        `).join('');
    });

    // --- 6. Settings Flow (D5) ---
    function populateModels() {
        const apiSelect = document.getElementById('select-api-model');
        const localSelect = document.getElementById('select-local-model');
        
        apiSelect.innerHTML = GEMMA_MODELS.api.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
        localSelect.innerHTML = GEMMA_MODELS.local.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
        
        const updateCost = () => {
            const selected = GEMMA_MODELS.api.find(m => m.id === apiSelect.value);
            document.getElementById('api-cost-est').innerText = `$${selected.cost.toFixed(5)}`;
        };
        
        apiSelect.addEventListener('change', updateCost);
        updateCost();
    }

    const tabApiBtn = document.getElementById('tab-btn-api');
    const tabLocalBtn = document.getElementById('tab-btn-local');
    const tabApiContent = document.getElementById('tab-api');
    const tabLocalContent = document.getElementById('tab-local');

    tabApiBtn.addEventListener('click', () => {
        tabApiBtn.classList.add('active');
        tabLocalBtn.classList.remove('active');
        tabApiContent.classList.remove('hidden');
        tabLocalContent.classList.add('hidden');
    });

    tabLocalBtn.addEventListener('click', () => {
        tabLocalBtn.classList.add('active');
        tabApiBtn.classList.remove('active');
        tabLocalContent.classList.remove('hidden');
        tabApiContent.classList.add('hidden');
    });

    document.getElementById('btn-save-settings').addEventListener('click', () => {
        const cap = document.getElementById('spend-cap').value;
        alert(`Settings Saved!\nMonthly Cap set to: $${cap}\nSelected Model: ${document.getElementById('select-api-model').value}`);
    });

    document.getElementById('nav-submit').addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('submit');
    });
});
