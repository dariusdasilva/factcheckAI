// popup.js - Logic for the extension popup window

document.addEventListener('DOMContentLoaded', async () => {
    const selectedTextEl = document.getElementById('selected-text');
    const verifyBtn = document.getElementById('btn-verify');
    const resultArea = document.getElementById('result-area');
    const setupWarning = document.getElementById('setup-warning');

    // 1. Check for API Key in storage
    const storage = await chrome.storage.local.get(['api_key']);
    if (!storage.api_key) {
        setupWarning.classList.remove('hidden');
        document.getElementById('main-ui').style.opacity = '0.5';
        document.getElementById('main-ui').style.pointerEvents = 'none';
    }

    document.getElementById('btn-go-options').addEventListener('click', () => {
        chrome.runtime.openOptionsPage();
    });

    // 2. Get selected text from the active tab
    async function updateSelection() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab) return;
        
        // Store tabId globally for later use in the verify click handler
        window.currentTabId = tab.id;

        chrome.tabs.sendMessage(tab.id, { action: "GET_SELECTION" }, (response) => {
            if (chrome.runtime.lastError || !response || !response.selection) {
                selectedTextEl.innerText = "Nothing selected... Please highlight some text on the page.";
                verifyBtn.disabled = true;
            } else {
                selectedTextEl.innerText = response.selection.substring(0, 100) + (response.selection.length > 100 ? '...' : '');
                verifyBtn.disabled = false;
            }
        });
    }

    // Update selection every time popup opens
    updateSelection();

    // 3. Handle Verification
    verifyBtn.addEventListener('click', async () => {
        const text = selectedTextEl.innerText;
        const tabId = window.currentTabId;
        if (verifyBtn.disabled || !tabId) return;

        verifyBtn.disabled = true;
        verifyBtn.innerText = "Verifying...";
        resultArea.innerHTML = "Connecting to brain...";

        try {
            // In a real app, this would be:
            // const response = await fetch('https://api.factcheckai.com/api/v1/checks/', { 
            //    method: 'POST', 
            //    headers: { 'Authorization': `Token ${storage.api_key}` },
            //    body: JSON.stringify({ claim: text })
            // });
            
            // For now, we'll mock the response just like the web app
            await new Promise(r => setTimeout(r, 1500));
            
            // Mock a random result
            const scenarios = ['success_remote', 'success_local', 'fail_state'];
            const scenario = scenarios[Math.floor(Math.random() * scenarios.length)];
            
            // We would normally fetch from our JSON mock here, but for the 
            // extension we'll simulate the data shape for the badge
            let mockData = { status: 'ok', verdict: 'false', confidence: 0.85 };
            if (scenario === 'fail_state') mockData = { status: 'fail_state' };
            if (scenario === 'success_local') mockData = { status: 'fallback', verdict: 'true', confidence: 0.60 };

            // Send the result to the CONTENT script to create the badge on the page
            chrome.tabs.sendMessage(tabId, { 
                action: "INJECT_BADGE", 
                data: mockData 
            });

            resultArea.innerHTML = `
                <div class="verdict-badge" style="background: ${mockData.status === 'fail_state' ? '#444' : '#10b981'}; color: #000;">${mockData.status === 'fail_state' ? 'DEGRADED' : 'VERDICT: ' + mockData.verdict.toUpperCase()}</div>
                <div style="color: #a1a1aa; font-size: 0.8rem;">Badge injected onto page!</div>
            `;
        } catch (e) {
            resultArea.innerHTML = `<div style="color: #ef4444;">Error connecting to server.</div>`;
        } finally {
            verifyBtn.disabled = false;
            verifyBtn.innerText = "Verify Selection";
        }
    });
});
