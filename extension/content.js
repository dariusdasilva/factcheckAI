// content.js - Runs in the web page
// Its only job is to listen for a request from the popup to get the selected text
// and to inject the verdict badge into the page.

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "GET_SELECTION") {
        const selection = window.getSelection().toString().trim();
        sendResponse({ selection: selection });
    }

    if (request.action === "INJECT_BADGE") {
        injectVerdictBadge(request.data);
    }
});

function injectVerdictBadge(data) {
    // 1. Find the coordinates of the selected text
    const selection = window.getSelection();
    if (selection.rangeCount === 0) return;
    
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    // 2. Create the badge element
    const badge = document.createElement('div');
    badge.id = 'factcheck-ai-badge';
    
    // Basic styles to make it look like the T3 design
    Object.assign(badge.style, {
        position: 'absolute',
        top: `${rect.top + window.scrollY - 45}px`,
        left: `${rect.left + window.scrollX}px`,
        backgroundColor: '#0a0a0a',
        color: '#ffffff',
        border: '1px solid #27272a',
        borderLeft: '4px solid #ff4655',
        padding: '8px 12px',
        borderRadius: '4px',
        fontSize: '13px',
        fontWeight: '600',
        zIndex: '999999',
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        pointerEvents: 'auto',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        fontFamily: 'Inter, sans-serif'
    });

    // 3. Handle Fail State vs Success
    if (data.status === 'fail_state') {
        badge.style.borderLeftColor = '#94a3b8';
        badge.innerHTML = `
            <span style="color: #a1a1aa;">⚠️ Service Degraded: Result Unavailable</span>
            <button id="fc-close" style="background:none; border:none; color:#fff; cursor:pointer; font-weight:bold;">×</button>
        `;
    } else {
        const verdictColor = data.verdict === 'true' ? '#10b981' : '#ef4444';
        badge.innerHTML = `
            <span style="color: ${verdictColor}; font-weight: 800; text-transform: uppercase;">${data.verdict}</span>
            <span style="color: #a1a1aa; font-weight: 400;">${(data.confidence * 100).toFixed(0)}% Confidence</span>
            <button id="fc-close" style="background:none; border:none; color:#fff; cursor:pointer; font-weight:bold; margin-left: 8px;">×</button>
        `;
    }

    document.body.appendChild(badge);

    // 4. Handle dismissal
    badge.querySelector('#fc-close').addEventListener('click', () => {
        badge.remove();
    });
}

