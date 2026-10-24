/**
 * api.js — The "Communicator"
 * This file handles all communication with the backend.
 * Currently, it uses a "Mock" (fake) brain so we can build the UI.
 */

const API_BASE = '/api/v1'; // The real URL we will use later
const MOCK_FILE = '/tests/mocks/api_responses.json'; // Where our pretend answers live

async function fetchMock(key) {
    console.log(`[API] Fetching mock data for: ${key}...`);
    try {
        const response = await fetch(MOCK_FILE);
        const data = await response.json();
        return data[key];
    } catch (e) {
        console.error(`[API] Error reading mock file: ${e}`);
        return null;
    }
}

const Api = {
    // Pretend to log in
    async login(username, password) {
        console.log(`[API] Attempting login for ${username}...`);
        // In a real app: POST /api/v1/auth/login
        // In mock: just return success if username isn't empty
        return new Promise((resolve) => {
            setTimeout(() => {
                if (username && password) {
                    resolve({ success: true, user: { username, token: 'fake-jwt-token' } });
                } else {
                    resolve({ success: false, message: 'Invalid credentials' });
                }
            }, 500);
        });
    },

    // Pretend to register
    async register(username, email, password) {
        console.log(`[API] Attempting to register ${username}...`);
        // In a real app: POST /api/v1/auth/register
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve({ success: true, message: 'Account created successfully!' });
            }, 500);
        });
    },

    // Get a fact check result
    async getCheckResult(claim) {
        console.log(`[API] Requesting check for: ${claim}...`);
        
        // For demo purposes, we'll rotate through the mock answers 
        // based on a random choice so you can see all UI states.
        const scenarios = ['success_remote', 'success_local', 'fail_state'];
        const randomScenario = scenarios[Math.floor(Math.random() * scenarios.length)];
        
        const result = await fetchMock(randomScenario);
        return result;
    },

    // Get user history
    async getHistory() {
        console.log(`[API] Fetching history...`);
        return [
            { id: 1, claim: "Drinking coffee cures colds", verdict: "false", date: "2026-10-23" },
            { id: 2, claim: "The moon is made of cheese", verdict: "false", date: "2026-10-22" },
            { id: 3, claim: "Water is wet", verdict: "true", date: "2026-10-21" },
        ];
    }
};
