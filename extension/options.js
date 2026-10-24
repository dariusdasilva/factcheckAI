document.addEventListener('DOMContentLoaded', async () => {
    const keyInput = document.getElementById('api_key');
    const capInput = document.getElementById('spend-cap');
    const apiSelect = document.getElementById('select-api-model');
    const localSelect = document.getElementById('select-local-model');
    const saveBtn = document.getElementById('save-btn');
    const statusEl = document.getElementById('status');

    const GEMMA_MODELS = {
        api: [
            { id: 'google/gemma-4-26b-a4b-it:free', name: 'Gemma 4 26B (Free)' },
            { id: 'google/gemma-4-26b-a4b-it', name: 'Gemma 4 26B (Paid)' },
            { id: 'google/gemma-4-31b-it:free', name: 'Gemma 4 31B (Free)' },
            { id: 'google/gemma-4-31b-it', name: 'Gemma 4 31B (Paid)' },
        ],
        local: [
            { id: 'gemma4:e4b-it-qat', name: 'Gemma 4 e4b (QAT)' },
            { id: 'gemma4:e2b-it-qat', name: 'Gemma 4 e2b (Low-Res)' },
        ]
    };

    // Populate dropdowns without innerHTML (no dynamic HTML injection).
    function populateSelect(select, models) {
        models.forEach(m => {
            const option = document.createElement('option');
            option.value = m.id;
            option.textContent = m.name;
            select.appendChild(option);
        });
    }
    populateSelect(apiSelect, GEMMA_MODELS.api);
    populateSelect(localSelect, GEMMA_MODELS.local);

    // Tab logic
    const tabApi = document.getElementById('tab-api');
    const tabLocal = document.getElementById('tab-local');
    const contentApi = document.getElementById('content-api');
    const contentLocal = document.getElementById('content-local');

    tabApi.addEventListener('click', () => {
        tabApi.classList.add('active');
        tabLocal.classList.remove('active');
        contentApi.classList.remove('hidden');
        contentLocal.classList.add('hidden');
    });

    tabLocal.addEventListener('click', () => {
        tabLocal.classList.add('active');
        tabApi.classList.remove('active');
        contentLocal.classList.remove('hidden');
        contentApi.classList.add('hidden');
    });

    // Load existing settings
    const storage = await chrome.storage.local.get(['api_key', 'spend_cap', 'api_model', 'local_model']);
    if (storage.api_key) keyInput.value = storage.api_key;
    if (storage.spend_cap) capInput.value = storage.spend_cap;
    if (storage.api_model) apiSelect.value = storage.api_model;
    if (storage.local_model) localSelect.value = storage.local_model;

    saveBtn.addEventListener('click', () => {
        const settings = {
            api_key: keyInput.value.trim(),
            spend_cap: capInput.value,
            api_model: apiSelect.value,
            local_model: localSelect.value
        };
        chrome.storage.local.set(settings, () => {
            statusEl.innerText = "Settings saved!";
            statusEl.style.color = "#10b981";
            setTimeout(() => { statusEl.innerText = ""; }, 3000);
        });
    });
});
