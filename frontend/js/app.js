// ==================== DYNAMIC BACKEND DETECTION ====================
// Automatically detect the correct backend API URL based on deployment environment

function getBackendUrl() {
    // Get the current script's location
    const scripts = document.getElementsByTagName('script');
    const currentScript = scripts[scripts.length - 1];
    
    // Try to get the current page URL
    let currentUrl = window.location.href;
    let currentOrigin = window.location.origin;
    let hostname = window.location.hostname;
    let port = window.location.port;
    
    // Strategy 1: Check for environment variable (set by backend)
    if (window.__BACKEND_URL__) {
        console.log('✅ Using backend from window.__BACKEND_URL__:', window.__BACKEND_URL__);
        return window.__BACKEND_URL__;
    }
    
    // Strategy 2: Check for meta tag with backend URL
    const metaBackend = document.querySelector('meta[name="backend-url"]');
    if (metaBackend && metaBackend.getAttribute('content')) {
        console.log('✅ Using backend from meta tag:', metaBackend.getAttribute('content'));
        return metaBackend.getAttribute('content');
    }
    
    // Strategy 3: Check localStorage for saved backend URL
    const savedBackend = localStorage.getItem('xrp_backend_url');
    if (savedBackend) {
        console.log('✅ Using backend from localStorage:', savedBackend);
        return savedBackend;
    }
    
    // Strategy 4: Detect if running on Render
    if (hostname.includes('onrender.com')) {
        // On Render, backend and frontend are on same domain
        const renderBackend = currentOrigin;
        console.log('✅ Detected Render deployment, using:', renderBackend);
        return renderBackend;
    }
    
    // Strategy 5: Check if we're on localhost/127.0.0.1
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1') {
        // Try common backend ports
        const possiblePorts = [5000, 5001, 8080, 8000, 3000];
        
        // If current port is already a backend port, use current origin
        if (possiblePorts.includes(parseInt(port))) {
            console.log('✅ Using current origin as backend:', currentOrigin);
            return currentOrigin;
        }
        
        // Otherwise, try to detect by attempting connections
        console.log('🔄 Attempting to detect backend on localhost...');
        return '/api'; // Relative path, assuming same server serves both
    }
    
    // Strategy 6: Check if running on GitHub Pages or static hosting
    if (hostname.includes('github.io') || hostname.includes('netlify.app') || hostname.includes('vercel.app')) {
        // For static hosting, backend is typically on a separate service
        // Try to extract from current domain pattern
        const parts = hostname.split('.');
        if (parts.length > 2) {
            const subdomain = parts[0];
            if (subdomain.includes('frontend') || subdomain.includes('ui')) {
                const backendSubdomain = subdomain.replace('frontend', 'backend').replace('ui', 'api');
                const backendUrl = `https://${backendSubdomain}.${parts.slice(1).join('.')}`;
                console.log('✅ Guessed backend URL from subdomain:', backendUrl);
                return backendUrl;
            }
        }
        
        // Default to Render-style URL if pattern matches
        const renderPattern = /(.*)-frontend\./;
        const match = hostname.match(renderPattern);
        if (match) {
            const backendUrl = `https://${match[1]}-backend.onrender.com`;
            console.log('✅ Guessed Render backend URL:', backendUrl);
            return backendUrl;
        }
    }
    
    // Strategy 7: Try relative path (same-origin deployment)
    console.log('✅ Using relative path /api (same-origin fallback)');
    return '/api';
}

// Strategy 8: Advanced - Try multiple possible backend URLs and use the first that responds
async function discoverBackendUrl() {
    const possibleUrls = [
        // Current origin with /api
        `${window.location.origin}/api`,
        
        // Current origin (full backend)
        window.location.origin,
        
        // Localhost variations
        'http://localhost:5000/api',
        'http://localhost:5000',
        'http://127.0.0.1:5000/api',
        'http://127.0.0.1:5000',
        'http://localhost:8080/api',
        'http://localhost:8080',
        'http://localhost:8000/api',
        'http://localhost:8000',
        
        // Check if on Render
        ...(window.location.hostname.includes('onrender.com') ? [
            window.location.origin,
            `https://${window.location.hostname.replace('-frontend', '-backend')}`,
            `https://${window.location.hostname.replace('-ui', '-api')}`
        ] : []),
        
        // Original hardcoded (fallback)
        'http://localhost:5000/api'
    ];
    
    // Remove duplicates
    const uniqueUrls = [...new Set(possibleUrls)];
    
    console.log('🔍 Discovering backend API from', uniqueUrls.length, 'possible URLs...');
    
    for (const url of uniqueUrls) {
        try {
            // Try to fetch the test endpoint
            const testUrl = `${url.replace(/\/$/, '')}/api/test`;
            console.log(`🔄 Testing: ${testUrl}`);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);
            
            const response = await fetch(testUrl, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'ok' || data.validation) {
                    const backendUrl = url.replace(/\/api$/, '').replace(/\/$/, '');
                    console.log('✅ Backend discovered at:', backendUrl);
                    
                    // Cache the discovered URL
                    localStorage.setItem('xrp_backend_url', backendUrl);
                    
                    // Store in window for global access
                    window.__BACKEND_URL__ = backendUrl;
                    
                    return backendUrl;
                }
            }
        } catch (error) {
            // Silently fail and try next URL
            console.log(`❌ Failed: ${url}`, error.message);
        }
    }
    
    // Fallback to relative path
    console.warn('⚠️ No backend discovered, using relative path /api');
    return '/api';
}

// Strategy 9: Manual backend configuration UI
function showBackendConfigModal() {
    let modal = document.getElementById('backendConfigModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'backendConfigModal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h2>🔧 Backend Configuration</h2>
                    <button onclick="closeBackendConfig()" class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <p>Configure the backend API URL for the XRP Scanner.</p>
                    <div class="input-group" style="margin: 20px 0;">
                        <label>Backend API URL:</label>
                        <input type="text" id="backendUrlInput" placeholder="http://localhost:5000" 
                               value="${localStorage.getItem('xrp_backend_url') || ''}" 
                               style="width: 100%; padding: 10px; margin-top: 8px;">
                        <small style="display: block; margin-top: 8px; color: var(--neutral-400);">
                            Example: http://localhost:5000 or https://xrp-scanner.onrender.com
                        </small>
                    </div>
                    <div class="button-group" style="display: flex; gap: 12px; margin-top: 20px;">
                        <button onclick="saveBackendConfig()" class="btn btn-primary" style="flex: 1;">Save & Test</button>
                        <button onclick="autoDiscoverBackend()" class="btn btn-secondary" style="flex: 1;">Auto-Discover</button>
                        <button onclick="closeBackendConfig()" class="btn btn-secondary">Cancel</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
}

function closeBackendConfig() {
    const modal = document.getElementById('backendConfigModal');
    if (modal) modal.style.display = 'none';
}

async function saveBackendConfig() {
    const input = document.getElementById('backendUrlInput');
    const url = input.value.trim().replace(/\/$/, '').replace(/\/api$/, '');
    
    if (!url) {
        showNotification('Please enter a valid URL', 'warning');
        return;
    }
    
    // Test the URL
    showNotification('Testing connection...', 'info');
    
    try {
        const testUrl = `${url}/api/test`;
        const response = await fetch(testUrl, { method: 'GET', headers: { 'Accept': 'application/json' } });
        
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'ok' || data.validation) {
                localStorage.setItem('xrp_backend_url', url);
                window.__BACKEND_URL__ = url;
                showNotification('✅ Backend configured successfully! Reloading...', 'success');
                setTimeout(() => location.reload(), 1500);
                return;
            }
        }
        throw new Error('Invalid backend response');
    } catch (error) {
        showNotification('❌ Connection failed: ' + error.message, 'error');
    }
}

async function autoDiscoverBackend() {
    showNotification('🔍 Running auto-discovery...', 'info');
    const backendUrl = await discoverBackendUrl();
    const input = document.getElementById('backendUrlInput');
    if (input) input.value = backendUrl;
    showNotification('✅ Discovery complete! Click Save to use this URL.', 'success');
}

// Set the global API_BASE dynamically
let API_BASE = '/api';
let API_READY = false;

// Initialize backend detection
async function initializeBackend() {
    console.log('🔍 Initializing backend detection...');
    
    // Try to discover backend
    const discoveredUrl = await discoverBackendUrl();
    API_BASE = discoveredUrl;
    
    // Add /api if not present
    if (!API_BASE.endsWith('/api') && !API_BASE.endsWith('/api/')) {
        API_BASE = `${API_BASE}/api`;
    }
    
    // Remove trailing slash
    API_BASE = API_BASE.replace(/\/$/, '');
    
    console.log('📍 API_BASE set to:', API_BASE);
    
    // Verify connection
    try {
        const response = await fetch(`${API_BASE}/test`);
        if (response.ok) {
            const data = await response.json();
            API_READY = true;
            console.log('✅ Backend API ready:', data);
            
            // Show connection status in UI
            updateConnectionStatus('connected', API_BASE);
            return true;
        }
    } catch (error) {
        console.error('❌ Backend connection failed:', error);
        updateConnectionStatus('disconnected', null);
        showBackendConfigModal();
        return false;
    }
}

// Update connection status in UI
function updateConnectionStatus(status, url) {
    let statusBadge = document.getElementById('connectionStatus');
    if (!statusBadge) {
        statusBadge = document.createElement('div');
        statusBadge.id = 'connectionStatus';
        statusBadge.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 500;
            z-index: 1000;
            cursor: pointer;
            background: var(--neutral-800);
            border: 1px solid var(--neutral-700);
            transition: all 0.3s;
        `;
        statusBadge.onclick = () => showBackendConfigModal();
        document.body.appendChild(statusBadge);
    }
    
    if (status === 'connected') {
        statusBadge.innerHTML = `✅ API: ${new URL(url).hostname}<br>🔗 Click to change`;
        statusBadge.style.borderLeft = '4px solid var(--success)';
    } else {
        statusBadge.innerHTML = '❌ API Disconnected<br>🔧 Click to configure';
        statusBadge.style.borderLeft = '4px solid var(--danger)';
    }
    
    // Auto-hide after 10 seconds
    setTimeout(() => {
        statusBadge.style.opacity = '0.7';
    }, 10000);
}

// Override fetch to use dynamic API_BASE
const originalFetch = window.fetch;
window.fetch = function(url, options) {
    // If URL is relative and starts with /api, prepend API_BASE
    if (typeof url === 'string' && url.startsWith('/api') && API_BASE && API_BASE !== '/api') {
        const newUrl = API_BASE + url;
        console.log(`🔄 Rewriting fetch: ${url} -> ${newUrl}`);
        return originalFetch(newUrl, options);
    }
    return originalFetch(url, options);
};

// ==================== API Configuration (Dynamic) ====================
const DEFAULT_EXPLORER = 'https://xrpscan.com/tx/';

// State Management
let activeScanId = null;
let scanPollInterval = null;
let liveFilesInterval = null;
let currentFiles = [];
let currentScanId = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('XRP Sentinel initializing...');
    
    // Initialize backend detection first
    const backendReady = await initializeBackend();
    
    if (backendReady) {
        await testAPIConnection();
        await refreshLogs();
        await loadAnalytics();
    }
    
    // Setup event listeners
    const walletInput = document.getElementById('walletAddress');
    if (walletInput) {
        walletInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                scanWallet();
            }
        });
    }
    
    const scanMode = document.getElementById('scanMode');
    if (scanMode) {
        scanMode.addEventListener('change', (e) => {
            const mode = e.target.value;
            const limitInput = document.getElementById('limit');
            if (limitInput) {
                limitInput.disabled = mode === 'large';
            }
        });
    }
});

// Test API Connection (using dynamic detection)
async function testAPIConnection() {
    try {
        // Use the dynamic API_BASE
        const response = await fetch(`${API_BASE}/test`);
        const data = await response.json();
        console.log('API Connection:', data);
        
        if (data.validation) {
            console.log('Blockchain validation enabled:', data.validation);
            showNotification('✅ Connected to blockchain-verified scanner', 'success');
        }
        if (data.features) {
            console.log('Available features:', data.features);
        }
        if (data.backend_url) {
            console.log('Backend URL:', data.backend_url);
        }
        if (data.frontend_url) {
            console.log('Frontend URL:', data.frontend_url);
        }
        
        return true;
    } catch (error) {
        console.error('API Connection failed:', error);
        showNotification('Cannot connect to backend API. Click the bottom-right badge to configure.', 'error');
        return false;
    }
}

// Helper function to get full API URL
function getApiUrl(endpoint) {
    const base = API_BASE.replace(/\/$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    return `${base}${cleanEndpoint}`;
}

// Show Notification (updated to handle dynamic connection)
function showNotification(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Format Hash
function formatHash(hash) {
    if (!hash) return 'N/A';
    return `${hash.substring(0, 6)}...${hash.substring(hash.length - 6)}`;
}

// Get Explorer Link
function getExplorerLink(hash) {
    if (!hash) return 'N/A';
    return `<a href="${DEFAULT_EXPLORER}${hash}" target="_blank" class="explorer-link">${formatHash(hash)}</a>`;
}

// Get Address Link
function getAddressLink(address) {
    if (!address) return 'N/A';
    return `<a href="https://xrpscan.com/account/${address}" target="_blank" class="explorer-link">${formatHash(address)}</a>`;
}

// Load Analytics
async function loadAnalytics() {
    try {
        const response = await fetch(`${API_BASE}/analytics/summary`);
        const data = await response.json();
        
        const elements = {
            totalScans: document.getElementById('totalScans'),
            totalXRP: document.getElementById('totalXRP'),
            totalMissing: document.getElementById('totalMissing'),
            avgMissing: document.getElementById('avgMissing')
        };
        
        if (elements.totalScans) elements.totalScans.textContent = data.total_scans || '0';
        if (elements.totalXRP) elements.totalXRP.textContent = 
            new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(data.total_xrp_at_risk || 0) + ' XRP';
        if (elements.totalMissing) elements.totalMissing.textContent = 
            new Intl.NumberFormat().format(data.total_missing_tags || 0);
        if (elements.avgMissing) elements.avgMissing.textContent = 
            (data.average_missing_per_scan || 0).toFixed(2);
        
        if (data.validation_method) {
            console.log('Analytics validation:', data.validation_method);
        }
    } catch (error) {
        console.error('Failed to load analytics:', error);
    }
}

// Scan Wallet
async function scanWallet() {
    const address = document.getElementById('walletAddress').value.trim();
    const limit = document.getElementById('limit').value;
    const mode = document.getElementById('scanMode').value;
    
    if (!address) {
        showNotification('Please enter a wallet address', 'warning');
        return;
    }
    
    if (!address.startsWith('r') || address.length < 25) {
        showNotification('Invalid XRP wallet address format', 'error');
        return;
    }
    
    if (mode === 'large') {
        startLargeScan();
        return;
    }
    
    const loadingDiv = document.getElementById('loading');
    const scanBtn = document.getElementById('scanBtn');
    const summarySection = document.getElementById('summarySection');
    
    if (loadingDiv) loadingDiv.style.display = 'flex';
    if (summarySection) summarySection.style.display = 'none';
    if (scanBtn) scanBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE}/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address, limit: parseInt(limit) })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayResults(data);
            await refreshLogs();
            await loadAnalytics();
            
            if (data.validation_info) {
                console.log('Blockchain validation performed:', data.validation_info.checks_performed);
                showNotification(`Blockchain-verified: Found ${data.transactions.length} transactions genuinely missing tags`, 'success');
            } else {
                showNotification(`Found ${data.transactions.length} transactions missing tags`, 'success');
            }
        } else {
            showNotification(data.error || 'Scan failed', 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    } finally {
        if (loadingDiv) loadingDiv.style.display = 'none';
        if (scanBtn) scanBtn.disabled = false;
    }
}

// Start Large Scan
async function startLargeScan() {
    const address = document.getElementById('walletAddress').value.trim();
    
    if (!address) {
        showNotification('Please enter a wallet address', 'warning');
        return;
    }
    
    if (!confirm(`🔍 Blockchain-Verified Large Scan\n\nThis will scan ALL transactions for ${address} with full XRPL validation.\n\n✅ Verifies:\n• Successful payments only (tesSUCCESS)\n• No DestinationTag\n• No Memos\n• Valid delivered amounts\n\nThis could take significant time for wallets with millions of transactions.\n\nDo you want to continue?`)) {
        return;
    }
    
    showNotification('Starting blockchain-verified large scan...', 'info');
    
    try {
        const response = await fetch(`${API_BASE}/scan/large`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentScanId = data.scan_id;
            activeScanId = data.scan_id;
            showNotification(`Large scan started! ID: ${data.scan_id} (Blockchain-validated)`, 'success');
            
            // Show live files panel
            showLiveFilesPanel();
            
            // Start real-time file streaming
            startLiveFileStreaming(data.scan_id);
            
            // Start progress polling
            pollScanStatus(data.scan_id);
            
            // Show file explorer button
            const explorerBtn = document.getElementById('explorerBtn');
            if (explorerBtn) explorerBtn.style.display = 'inline-flex';
        } else {
            showNotification(data.error || 'Failed to start scan', 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}

// Show Live Files Panel
function showLiveFilesPanel() {
    let panel = document.getElementById('liveFilesPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'liveFilesPanel';
        panel.className = 'panel live-files-panel';
        const scanPanel = document.querySelector('.scan-panel');
        if (scanPanel) {
            scanPanel.insertAdjacentElement('afterend', panel);
        } else {
            document.querySelector('.container')?.appendChild(panel);
        }
        
        panel.innerHTML = `
            <div class="panel-header">
                <h2>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    Live Files Streaming
                </h2>
                <span class="live-badge" style="background: #ef4444;">
                    <span class="pulse"></span>
                    LIVE
                </span>
            </div>
            <div class="panel-body">
                <div id="liveFilesList" class="live-files-list">
                    <div class="empty-state">Waiting for scan to start...</div>
                </div>
            </div>
        `;
    }
    
    panel.style.display = 'block';
}

// Start Live File Streaming
function startLiveFileStreaming(scanId) {
    if (liveFilesInterval) {
        clearInterval(liveFilesInterval);
    }
    
    liveFilesInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/scan/status/${scanId}`);
            const data = await response.json();
            
            if (response.ok && data.live_files && data.live_files.length > 0) {
                updateLiveFilesList(data.live_files, data);
            }
        } catch (error) {
            console.error('Error fetching live files:', error);
        }
    }, 3000);
}

// Update Live Files List
function updateLiveFilesList(files, scanData) {
    const container = document.getElementById('liveFilesList');
    if (!container) return;
    
    if (files.length === 0) {
        container.innerHTML = '<div class="empty-state">No files generated yet...</div>';
        return;
    }
    
    const filesHtml = files.map(file => `
        <div class="live-file-item">
            <div class="live-file-info">
                <span class="live-file-icon">${file.filename.endsWith('.csv') ? '📊' : '📄'}</span>
                <div class="live-file-details">
                    <div class="live-file-name">${file.filename}</div>
                    <div class="live-file-meta">
                        ${formatFileSize(file.size)} • ${new Date(file.created_at).toLocaleTimeString()}
                    </div>
                </div>
            </div>
            <div class="live-file-actions">
                <button onclick="downloadFile('${file.filename}')" class="file-btn-small" title="Download">
                    💾
                </button>
                <button onclick="viewFile('${file.filename}')" class="file-btn-small" title="Preview">
                    👁️
                </button>
                <button onclick="openLivePreview('${file.view_url}')" class="file-btn-small" title="Live View">
                    🔍
                </button>
            </div>
        </div>
    `).join('');
    
    // Add scan stats header
    const statsHtml = `
        <div class="live-stats">
            <div class="live-stat">
                <span class="live-stat-label">Processed:</span>
                <span class="live-stat-value">${(scanData.processed || 0).toLocaleString()}</span>
            </div>
            <div class="live-stat">
                <span class="live-stat-label">Missing:</span>
                <span class="live-stat-value">${scanData.missing || 0}</span>
            </div>
            <div class="live-stat">
                <span class="live-stat-label">Total XRP:</span>
                <span class="live-stat-value">${(scanData.total_amount || 0).toFixed(2)}</span>
            </div>
            <div class="live-stat">
                <span class="live-stat-label">Files:</span>
                <span class="live-stat-value">${files.length}</span>
            </div>
        </div>
        <div class="live-files-container">
            ${filesHtml}
        </div>
    `;
    
    container.innerHTML = statsHtml;
    currentFiles = files;
}

// Open Live Preview
function openLivePreview(viewUrl) {
    let modal = document.getElementById('livePreviewModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'livePreviewModal';
        modal.className = 'modal';
        document.body.appendChild(modal);
        
        modal.innerHTML = `
            <div class="modal-content modal-preview">
                <div class="modal-header">
                    <h2>File Preview</h2>
                    <button onclick="closePreviewModal()" class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <iframe id="livePreviewFrame" src="about:blank" style="width: 100%; height: 80vh; border: none; border-radius: 8px;"></iframe>
                </div>
            </div>
        `;
    }
    
    const iframe = document.getElementById('livePreviewFrame');
    iframe.src = viewUrl;
    modal.style.display = 'flex';
}

// Close Preview Modal
function closePreviewModal() {
    const modal = document.getElementById('livePreviewModal');
    if (modal) {
        modal.style.display = 'none';
        const iframe = document.getElementById('livePreviewFrame');
        if (iframe) iframe.src = 'about:blank';
    }
}

// Poll Scan Status
function pollScanStatus(scanId) {
    const progressDiv = document.getElementById('scanProgress');
    if (progressDiv) progressDiv.style.display = 'block';
    
    if (scanPollInterval) {
        clearInterval(scanPollInterval);
    }
    
    scanPollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/scan/status/${scanId}`);
            const status = await response.json();
            
            if (response.ok) {
                updateScanProgress(status);
                
                // Update live files from status
                if (status.live_files && status.live_files.length > 0) {
                    updateLiveFilesList(status.live_files, status);
                }
                
                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(scanPollInterval);
                    scanPollInterval = null;
                    
                    if (liveFilesInterval) {
                        clearInterval(liveFilesInterval);
                        liveFilesInterval = null;
                    }
                    
                    if (status.status === 'completed') {
                        showNotification(`✅ Scan completed! Blockchain verification found ${status.missing} transactions missing tags`, 'success');
                        await refreshLogs();
                        await loadAnalytics();
                        
                        if (status.downloads && status.downloads.length > 0) {
                            showFileDownloadPanel(status.downloads);
                        }
                        
                        setTimeout(() => {
                            if (progressDiv) progressDiv.style.display = 'none';
                        }, 5000);
                    } else if (status.status === 'error') {
                        showNotification(`Scan error: ${status.error}`, 'error');
                    }
                }
            } else if (response.status === 404) {
                clearInterval(scanPollInterval);
                scanPollInterval = null;
                if (liveFilesInterval) {
                    clearInterval(liveFilesInterval);
                    liveFilesInterval = null;
                }
                if (progressDiv) progressDiv.style.display = 'none';
                showNotification('Scan not found or expired', 'warning');
            }
        } catch (error) {
            console.error('Status poll error:', error);
        }
    }, 2000);
}

// Show File Download Panel
function showFileDownloadPanel(files) {
    currentFiles = files;
    
    let panel = document.getElementById('fileDownloadPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'fileDownloadPanel';
        panel.className = 'file-download-panel';
        const summarySection = document.getElementById('summarySection');
        if (summarySection) {
            summarySection.insertAdjacentElement('afterend', panel);
        } else {
            document.querySelector('.container')?.appendChild(panel);
        }
    }
    
    const filesHtml = files.map(file => `
        <div class="file-item">
            <div class="file-info">
                <span class="file-icon">${file.type === 'json' ? '📄' : '📊'}</span>
                <div class="file-details">
                    <span class="file-name">${file.filename}</span>
                    <span class="file-size">${formatFileSize(file.size)}</span>
                    <span class="file-date">${new Date(file.created_at).toLocaleString()}</span>
                </div>
            </div>
            <div class="file-actions">
                <button onclick="downloadFile('${file.filename}')" class="file-btn download-btn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download
                </button>
                <button onclick="viewFile('${file.filename}')" class="file-btn view-btn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                    </svg>
                    View
                </button>
            </div>
        </div>
    `).join('');
    
    panel.innerHTML = `
        <div class="panel-header">
            <h3>📁 Generated Files (${files.length})</h3>
            <button onclick="closeFilePanel()" class="close-panel-btn">×</button>
        </div>
        <div class="files-list">
            ${filesHtml}
        </div>
        <div class="panel-actions">
            <button onclick="openFileExplorer('${activeScanId}')" class="explorer-btn">
                🗂️ Open File Explorer
            </button>
            <button onclick="downloadAllFiles()" class="download-all-btn">
                📦 Download All
            </button>
        </div>
    `;
    
    panel.style.display = 'block';
}

// Format File Size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Download File
async function downloadFile(filename) {
    try {
        const response = await fetch(`${API_BASE}/files/${filename}`);
        if (!response.ok) {
            throw new Error('Download failed');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showNotification(`Downloaded ${filename}`, 'success');
    } catch (error) {
        showNotification('Download failed: ' + error.message, 'error');
    }
}

// View File in Browser
function viewFile(filename) {
    const viewUrl = `${API_BASE}/files/view/${filename}`;
    window.open(viewUrl, '_blank');
}

// Open File Explorer
async function openFileExplorer(scanId) {
    try {
        const response = await fetch(`${API_BASE}/files/explorer/${scanId}`);
        const data = await response.json();
        
        if (response.ok) {
            showFileExplorerModal(data);
        } else {
            showNotification('Failed to load file explorer', 'error');
        }
    } catch (error) {
        showNotification('Error opening file explorer', 'error');
    }
}

// Show File Explorer Modal
function showFileExplorerModal(data) {
    let modal = document.getElementById('fileExplorerModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'fileExplorerModal';
        modal.className = 'modal';
        document.body.appendChild(modal);
    }
    
    const filesHtml = (data.files || []).map(file => `
        <div class="explorer-file-item">
            <div class="explorer-file-info">
                <span class="explorer-file-icon">${file.type === 'json' ? '📄' : '📊'}</span>
                <div>
                    <div class="explorer-file-name">${file.filename}</div>
                    <div class="explorer-file-meta">${formatFileSize(file.size)} • ${new Date(file.created_at).toLocaleString()}</div>
                </div>
            </div>
            <div class="explorer-file-actions">
                <button onclick="downloadFile('${file.filename}')" class="file-btn-small">Download</button>
                <button onclick="viewFile('${file.filename}')" class="file-btn-small">View</button>
            </div>
        </div>
    `).join('');
    
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>📁 File Explorer - ${data.scan_id}</h2>
                <button onclick="closeModal()" class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="explorer-stats">
                    <div>Wallet: <strong>${data.wallet || 'Unknown'}</strong></div>
                    <div>Total Files: <strong>${data.total_files || 0}</strong></div>
                    <div>Total Size: <strong>${formatFileSize(data.total_size_bytes || 0)}</strong></div>
                    ${data.scan_stats ? `
                        <div>Status: <strong>${data.scan_stats.status}</strong></div>
                        <div>Processed: <strong>${data.scan_stats.processed?.toLocaleString() || 0}</strong></div>
                        <div>Missing: <strong>${data.scan_stats.missing || 0}</strong></div>
                    ` : ''}
                </div>
                <div class="explorer-files-list">
                    ${filesHtml || '<div class="empty-state">No files found</div>'}
                </div>
            </div>
        </div>
    `;
    
    modal.style.display = 'flex';
}

// Close Modal
function closeModal() {
    const modal = document.getElementById('fileExplorerModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Close File Panel
function closeFilePanel() {
    const panel = document.getElementById('fileDownloadPanel');
    if (panel) {
        panel.style.display = 'none';
    }
}

// Download All Files as ZIP
async function downloadAllFiles() {
    if (!currentFiles || currentFiles.length === 0) {
        showNotification('No files to download', 'warning');
        return;
    }
    
    showNotification('Preparing files for download...', 'info');
    
    try {
        for (const file of currentFiles) {
            setTimeout(() => {
                downloadFile(file.filename);
            }, 1000);
        }
        
        showNotification(`Starting download of ${currentFiles.length} files`, 'success');
    } catch (error) {
        showNotification('Error downloading files', 'error');
    }
}

// Update Scan Progress
function updateScanProgress(status) {
    const progressDiv = document.getElementById('scanProgress');
    if (!progressDiv) return;
    
    const percent = status.progress || 0;
    
    const percentEl = progressDiv.querySelector('.progress-percentage');
    const barEl = progressDiv.querySelector('.progress-bar');
    const statsEl = progressDiv.querySelector('.progress-stats');
    const statusEl = progressDiv.querySelector('.progress-status');
    
    if (percentEl) percentEl.textContent = `${percent.toFixed(1)}%`;
    if (barEl) barEl.style.width = `${percent}%`;
    
    const validationBadge = status.validation ? '<span class="validation-badge">🔗 Blockchain Verified</span>' : '';
    
    if (statsEl) {
        statsEl.innerHTML = `
            <span>📊 Processed: ${status.processed?.toLocaleString() || 0}</span>
            <span>⚠️ Missing: ${status.missing || 0}</span>
            <span>💰 Total: ${(status.total_amount || 0).toFixed(2)} XRP</span>
            ${validationBadge}
        `;
    }
    
    if (statusEl) {
        statusEl.innerHTML = `Status: ${status.status} ${status.validation ? '| Blockchain Validation Active' : ''}`;
    }
    
    if (status.status === 'completed' && status.downloads && status.downloads.length > 0) {
        showFileDownloadPanel(status.downloads);
    }
}

// Display Results
function displayResults(data) {
    const transactions = data.transactions || [];
    const summary = data.summary || {};
    const validationInfo = data.validation_info || {};
    
    const summarySection = document.getElementById('summarySection');
    const resultCount = document.getElementById('resultCount');
    const statsGrid = document.getElementById('statsGrid');
    const tableBody = document.getElementById('tableBody');
    
    if (summarySection) summarySection.style.display = 'block';
    if (resultCount) resultCount.textContent = `${transactions.length} found (Blockchain-Verified)`;
    
    const validationBadge = validationInfo.method ? 
        `<div class="validation-badge" style="margin-bottom: 16px; text-align: center; padding: 8px; background: var(--success); border-radius: 8px; color: white;">
            🔗 ${validationInfo.method} - ${validationInfo.checks_performed ? validationInfo.checks_performed.length : 0} checks performed
        </div>` : '';
    
    if (statsGrid) {
        statsGrid.innerHTML = validationBadge + `
            <div class="stat-card">
                <div class="stat-icon blue">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                        <line x1="8" y1="21" x2="16" y2="21"/>
                        <line x1="12" y1="17" x2="12" y2="21"/>
                    </svg>
                </div>
                <div class="stat-details">
                    <span class="stat-label">Scanned</span>
                    <span class="stat-value">${summary.total_transactions_scanned || 0}</span>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon orange">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                </div>
                <div class="stat-details">
                    <span class="stat-label">Missing (Verified)</span>
                    <span class="stat-value">${summary.missing_tag_count || 0}</span>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon green">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="1" x2="12" y2="23"/>
                        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                    </svg>
                </div>
                <div class="stat-details">
                    <span class="stat-label">Total XRP</span>
                    <span class="stat-value">${(summary.total_amount_missing_tags || 0).toFixed(2)}</span>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon purple">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                </div>
                <div class="stat-details">
                    <span class="stat-label">Latest</span>
                    <span class="stat-value">${summary.newest_transaction ? new Date(summary.newest_transaction).toLocaleDateString() : 'N/A'}</span>
                </div>
            </div>
        `;
    }
    
    if (!tableBody) return;
    
    if (transactions.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">✅ No transactions found missing destination tags - all payments have proper routing information!</td></tr>';
        return;
    }
    
    tableBody.innerHTML = transactions.map(tx => `
        <tr>
            <td>${new Date(tx.date).toLocaleString()}</td>
            <td>${getExplorerLink(tx.hash)}</td>
            <td>${getAddressLink(tx.sender)}</td>
            <td class="amount">${tx.amount.toFixed(6)} XRP</td>
            <td><span class="tag-missing">⚠️ MISSING</span><br><small style="font-size: 10px;">${tx.validation_status || 'blockchain-verified'}</small></td>
            <td>
                <a href="https://xrpscan.com/tx/${tx.hash}" target="_blank" class="explorer-badge">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                    View on XRPScan
                </a>
               </td>
           </tr>
    `).join('');
}

// Download Data
async function downloadData(format) {
    try {
        const response = await fetch(`${API_BASE}/download/${format}`);
        
        if (!response.ok) {
            showNotification('No data available to download', 'warning');
            return;
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'csv' ? 'xrp_transactions_blockchain_verified.csv' : 'scan_history_blockchain_verified.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showNotification(`Downloaded ${format.toUpperCase()} file with blockchain-verified data`, 'success');
    } catch (error) {
        showNotification('Download failed: ' + error.message, 'error');
    }
}

// Refresh Logs
async function refreshLogs() {
    try {
        const response = await fetch(`${API_BASE}/logs`);
        const data = await response.json();
        
        const logsContainer = document.getElementById('logsContainer');
        if (!logsContainer) return;
        
        if (data.logs && data.logs.length > 0) {
            logsContainer.innerHTML = data.logs.reverse().map(log => `
                <div class="log-entry">
                    <span class="log-timestamp">${new Date(log.timestamp).toLocaleString()}</span>
                    <span>
                        ${log.validation_type === 'blockchain_verified' ? '🔗' : '📊'} 
                        Scanned <strong>${formatHash(log.wallet || log.address || '')}</strong>: 
                        found <strong style="color: ${(log.transactions_found || log.missing_tags_found || 0) > 0 ? 'var(--danger)' : 'var(--success)'}">
                            ${log.transactions_found || log.missing_tags_found || 0}
                        </strong> missing tags 
                        ${log.validation_type === 'blockchain_verified' ? '<span style="font-size: 10px; background: var(--success); padding: 2px 6px; border-radius: 4px;">verified</span>' : ''}
                        ${log.files_generated ? `<span style="font-size: 10px; background: var(--info); padding: 2px 6px; border-radius: 4px;">${log.files_generated} files</span>` : ''}
                    </span>
                </div>
            `).join('');
        } else {
            logsContainer.innerHTML = '<div class="empty-state">No scan history available</div>';
        }
    } catch (error) {
        console.error('Failed to refresh logs:', error);
    }
}

// Add the CSS styles (same as before - included in the original)
// ... (keep all the CSS styles from the original)

// Expose functions globally
window.scanWallet = scanWallet;
window.downloadData = downloadData;
window.downloadFile = downloadFile;
window.viewFile = viewFile;
window.openFileExplorer = openFileExplorer;
window.closeModal = closeModal;
window.closeFilePanel = closeFilePanel;
window.downloadAllFiles = downloadAllFiles;
window.closePreviewModal = closePreviewModal;
window.openLivePreview = openLivePreview;
window.showBackendConfig = showBackendConfigModal;
window.saveBackendConfig = saveBackendConfig;
window.autoDiscoverBackend = autoDiscoverBackend;
window.closeBackendConfig = closeBackendConfig;
