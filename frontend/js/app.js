// API Configuration
const API_BASE = 'http://localhost:5000/api';
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
    await testAPIConnection();
    await refreshLogs();
    await loadAnalytics();
    
    // Setup event listeners
    document.getElementById('walletAddress').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            scanWallet();
        }
    });
    
    document.getElementById('scanMode').addEventListener('change', (e) => {
        const mode = e.target.value;
        document.getElementById('limit').disabled = mode === 'large';
    });
});

// Test API Connection
async function testAPIConnection() {
    try {
        const response = await fetch(`${API_BASE}/test`);
        const data = await response.json();
        console.log('API Connection:', data);
        if (data.validation) {
            console.log('Blockchain validation enabled:', data.validation);
        }
        if (data.features) {
            console.log('Available features:', data.features);
        }
        return true;
    } catch (error) {
        console.error('API Connection failed:', error);
        showNotification('Cannot connect to backend API', 'error');
        return false;
    }
}

// Show Notification
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
        
        document.getElementById('totalScans').textContent = data.total_scans || '0';
        document.getElementById('totalXRP').textContent = 
            new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(data.total_xrp_at_risk || 0) + ' XRP';
        document.getElementById('totalMissing').textContent = 
            new Intl.NumberFormat().format(data.total_missing_tags || 0);
        document.getElementById('avgMissing').textContent = 
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
    
    document.getElementById('loading').style.display = 'flex';
    document.getElementById('summarySection').style.display = 'none';
    document.getElementById('scanBtn').disabled = true;
    
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
        document.getElementById('loading').style.display = 'none';
        document.getElementById('scanBtn').disabled = false;
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
            document.getElementById('explorerBtn').style.display = 'inline-flex';
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
        scanPanel.insertAdjacentElement('afterend', panel);
        
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
    progressDiv.style.display = 'block';
    
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
                            progressDiv.style.display = 'none';
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
                progressDiv.style.display = 'none';
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
        document.getElementById('summarySection').insertAdjacentElement('afterend', panel);
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
    
    const filesHtml = data.files.map(file => `
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
    const percent = status.progress || 0;
    
    progressDiv.querySelector('.progress-percentage').textContent = `${percent.toFixed(1)}%`;
    progressDiv.querySelector('.progress-bar').style.width = `${percent}%`;
    
    const validationBadge = status.validation ? '<span class="validation-badge">🔗 Blockchain Verified</span>' : '';
    
    progressDiv.querySelector('.progress-stats').innerHTML = `
        <span>📊 Processed: ${status.processed?.toLocaleString() || 0}</span>
        <span>⚠️ Missing: ${status.missing || 0}</span>
        <span>💰 Total: ${(status.total_amount || 0).toFixed(2)} XRP</span>
        ${validationBadge}
    `;
    
    progressDiv.querySelector('.progress-status').innerHTML = `Status: ${status.status} ${status.validation ? '| Blockchain Validation Active' : ''}`;
    
    if (status.status === 'completed' && status.downloads && status.downloads.length > 0) {
        showFileDownloadPanel(status.downloads);
    }
}

// Display Results
function displayResults(data) {
    const transactions = data.transactions || [];
    const summary = data.summary || {};
    const validationInfo = data.validation_info || {};
    
    document.getElementById('summarySection').style.display = 'block';
    document.getElementById('resultCount').textContent = `${transactions.length} found (Blockchain-Verified)`;
    
    const validationBadge = validationInfo.method ? 
        `<div class="validation-badge" style="margin-bottom: 16px; text-align: center; padding: 8px; background: var(--success); border-radius: 8px; color: white;">
            🔗 ${validationInfo.method} - ${validationInfo.checks_performed ? validationInfo.checks_performed.length : 0} checks performed
        </div>` : '';
    
    document.getElementById('statsGrid').innerHTML = validationBadge + `
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
    
    const tableBody = document.getElementById('tableBody');
    
    if (transactions.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">✅ No transactions found missing destination tags - all payments have proper routing information!</td></table>';
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

// Add styles for live files panel
const style = document.createElement('style');
style.textContent = `
    .toast {
        position: fixed;
        top: 24px;
        right: 24px;
        padding: 12px 20px;
        background: var(--neutral-900);
        border: 1px solid var(--neutral-800);
        border-radius: 8px;
        box-shadow: var(--shadow-lg);
        z-index: 1100;
        animation: slideIn 0.3s ease;
    }
    
    .toast-success { border-left: 4px solid var(--success); }
    .toast-error { border-left: 4px solid var(--danger); }
    .toast-warning { border-left: 4px solid var(--warning); }
    .toast-info { border-left: 4px solid var(--info); }
    .toast.fade-out { animation: fadeOut 0.3s ease forwards; }
    
    .validation-badge {
        display: inline-block;
        background: linear-gradient(135deg, var(--success), var(--info));
        color: white;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        margin-left: 8px;
    }
    
    .tag-missing {
        background: var(--danger);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
    }
    
    /* Live Files Panel */
    .live-files-panel {
        margin-bottom: 24px;
    }
    
    .live-stats {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        padding: 16px;
        background: var(--neutral-900);
        border-radius: 8px;
        margin-bottom: 16px;
    }
    
    .live-stat {
        text-align: center;
    }
    
    .live-stat-label {
        display: block;
        font-size: 11px;
        color: var(--neutral-400);
        margin-bottom: 4px;
    }
    
    .live-stat-value {
        display: block;
        font-size: 18px;
        font-weight: 700;
        color: var(--primary);
    }
    
    .live-files-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 300px;
        overflow-y: auto;
    }
    
    .live-file-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        background: var(--neutral-800);
        border-radius: 8px;
        transition: all 0.2s;
        border: 1px solid var(--neutral-700);
    }
    
    .live-file-item:hover {
        background: var(--neutral-700);
        transform: translateX(4px);
    }
    
    .live-file-info {
        display: flex;
        align-items: center;
        gap: 12px;
        flex: 1;
    }
    
    .live-file-icon {
        font-size: 24px;
    }
    
    .live-file-name {
        font-size: 13px;
        font-weight: 500;
        color: var(--neutral-100);
        margin-bottom: 4px;
    }
    
    .live-file-meta {
        font-size: 11px;
        color: var(--neutral-400);
    }
    
    .live-file-actions {
        display: flex;
        gap: 8px;
    }
    
    .file-btn-small {
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 14px;
        cursor: pointer;
        border: none;
        background: var(--neutral-600);
        color: white;
        transition: all 0.2s;
    }
    
    .file-btn-small:hover {
        background: var(--neutral-500);
        transform: scale(1.05);
    }
    
    /* File Download Panel */
    .file-download-panel {
        background: var(--neutral-800);
        border-radius: 12px;
        margin: 20px 0;
        overflow: hidden;
        border: 1px solid var(--neutral-700);
        animation: slideDown 0.3s ease;
    }
    
    .panel-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        background: var(--neutral-900);
        border-bottom: 1px solid var(--neutral-700);
    }
    
    .panel-header h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
    }
    
    .close-panel-btn {
        background: none;
        border: none;
        color: var(--neutral-400);
        font-size: 24px;
        cursor: pointer;
        padding: 0;
        width: 30px;
        height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
        transition: all 0.2s;
    }
    
    .close-panel-btn:hover {
        background: var(--neutral-700);
        color: var(--neutral-100);
    }
    
    .files-list {
        max-height: 400px;
        overflow-y: auto;
    }
    
    .file-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 20px;
        border-bottom: 1px solid var(--neutral-700);
        transition: background 0.2s;
    }
    
    .file-item:hover {
        background: var(--neutral-700);
    }
    
    .file-info {
        display: flex;
        align-items: center;
        gap: 12px;
        flex: 1;
    }
    
    .file-icon {
        font-size: 24px;
    }
    
    .file-details {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    
    .file-name {
        font-size: 14px;
        font-weight: 500;
        color: var(--neutral-100);
    }
    
    .file-size, .file-date {
        font-size: 12px;
        color: var(--neutral-400);
    }
    
    .file-actions {
        display: flex;
        gap: 8px;
    }
    
    .file-btn {
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        border: none;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    .download-btn {
        background: var(--success);
        color: white;
    }
    
    .download-btn:hover {
        background: #0d9488;
        transform: translateY(-1px);
    }
    
    .view-btn {
        background: var(--info);
        color: white;
    }
    
    .view-btn:hover {
        background: #2563eb;
        transform: translateY(-1px);
    }
    
    .panel-actions {
        padding: 16px 20px;
        background: var(--neutral-900);
        border-top: 1px solid var(--neutral-700);
        display: flex;
        gap: 12px;
    }
    
    .explorer-btn, .download-all-btn {
        padding: 8px 16px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        border: none;
        flex: 1;
    }
    
    .explorer-btn {
        background: var(--primary);
        color: white;
    }
    
    .download-all-btn {
        background: var(--neutral-700);
        color: var(--neutral-100);
    }
    
    .explorer-btn:hover, .download-all-btn:hover {
        transform: translateY(-1px);
    }
    
    /* Modal Styles */
    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        z-index: 2000;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
    }
    
    .modal-content {
        background: var(--neutral-800);
        border-radius: 16px;
        max-width: 800px;
        width: 90%;
        max-height: 80vh;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        animation: slideUp 0.3s ease;
    }
    
    .modal-preview {
        max-width: 1200px;
        width: 95%;
        max-height: 90vh;
    }
    
    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 20px;
        border-bottom: 1px solid var(--neutral-700);
    }
    
    .modal-header h2 {
        margin: 0;
        font-size: 20px;
    }
    
    .modal-close {
        background: none;
        border: none;
        color: var(--neutral-400);
        font-size: 28px;
        cursor: pointer;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
    }
    
    .modal-close:hover {
        background: var(--neutral-700);
        color: var(--neutral-100);
    }
    
    .modal-body {
        padding: 20px;
        overflow-y: auto;
    }
    
    .explorer-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 16px;
        padding: 16px;
        background: var(--neutral-900);
        border-radius: 8px;
        margin-bottom: 20px;
    }
    
    .explorer-files-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    
    .explorer-file-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        background: var(--neutral-900);
        border-radius: 8px;
        transition: background 0.2s;
    }
    
    .explorer-file-item:hover {
        background: var(--neutral-700);
    }
    
    .explorer-file-info {
        display: flex;
        align-items: center;
        gap: 12px;
        flex: 1;
    }
    
    .explorer-file-icon {
        font-size: 28px;
    }
    
    .explorer-file-name {
        font-weight: 500;
        margin-bottom: 4px;
    }
    
    .explorer-file-meta {
        font-size: 12px;
        color: var(--neutral-400);
    }
    
    .explorer-file-actions {
        display: flex;
        gap: 8px;
    }
    
    @keyframes slideDown {
        from {
            opacity: 0;
            transform: translateY(-20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes slideUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }
    
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes fadeOut {
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;

document.head.appendChild(style);

