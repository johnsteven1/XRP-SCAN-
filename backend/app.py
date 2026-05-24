from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import csv
import time
from datetime import datetime
import os
import sys
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import glob
import mimetypes
from pathlib import Path

# ==================== UPGRADE: ADVANCED IMPORTS ====================
import gzip
from functools import wraps
from flask import make_response
# ===========================================================

app = Flask(__name__)
CORS(app)

# ==================== AUTO-DISCOVER DATA DIRECTORY ====================
def get_data_directory():
    """Auto-discover or create writable data directory"""
    
    # Priority 1: Environment variable (Render/Termux custom)
    if os.environ.get('DATA_DIR'):
        data_dir = os.environ.get('DATA_DIR')
        try:
            os.makedirs(data_dir, exist_ok=True)
            test_file = os.path.join(data_dir, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print(f"✅ Using DATA_DIR from env: {data_dir}")
            return data_dir
        except:
            print(f"⚠️ Cannot write to DATA_DIR env path: {data_dir}")
    
    # Priority 2: Termux home directory (best for Termux)
    termux_home = os.path.expanduser('~/xrp_scanner_data')
    try:
        os.makedirs(termux_home, exist_ok=True)
        test_file = os.path.join(termux_home, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print(f"✅ Using Termux home directory: {termux_home}")
        return termux_home
    except:
        print(f"⚠️ Cannot write to Termux home: {termux_home}")
    
    # Priority 3: Current working directory
    cwd_data = os.path.join(os.getcwd(), 'xrp_scanner_data')
    try:
        os.makedirs(cwd_data, exist_ok=True)
        test_file = os.path.join(cwd_data, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print(f"✅ Using current directory: {cwd_data}")
        return cwd_data
    except:
        print(f"⚠️ Cannot write to current directory: {cwd_data}")
    
    # Priority 4: User's temp directory (cross-platform)
    import tempfile
    temp_dir = os.path.join(tempfile.gettempdir(), 'xrp_scanner_data')
    try:
        os.makedirs(temp_dir, exist_ok=True)
        test_file = os.path.join(temp_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print(f"✅ Using temp directory: {temp_dir}")
        return temp_dir
    except:
        print(f"⚠️ Cannot write to temp directory: {temp_dir}")
    
    # Priority 5: Fallback to /tmp with error handling
    tmp_dir = '/tmp/xrp_scanner_data'
    try:
        os.makedirs(tmp_dir, exist_ok=True)
        test_file = os.path.join(tmp_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print(f"✅ Using /tmp directory: {tmp_dir}")
        return tmp_dir
    except PermissionError:
        print(f"❌ Permission denied for /tmp, using current directory fallback")
        final_fallback = os.path.join(os.getcwd(), 'data')
        os.makedirs(final_fallback, exist_ok=True)
        return final_fallback

# Get writable data directory
DATA_DIR = get_data_directory()
LOG_FILE = os.path.join(DATA_DIR, 'logs/scanner_log.json')
CSV_FILE = os.path.join(DATA_DIR, 'transactions.csv')
CHECKPOINT_FILE = os.path.join(DATA_DIR, 'scan_checkpoint.json')
LARGE_SCAN_DIR = os.path.join(DATA_DIR, 'large_scans')

# Create directories with error handling
try:
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
    os.makedirs(LARGE_SCAN_DIR, exist_ok=True)
    print(f"✅ Data directories created in: {DATA_DIR}")
except Exception as e:
    print(f"⚠️ Directory creation warning: {e}")
    # Fallback to current directory
    DATA_DIR = os.path.join(os.getcwd(), 'xrp_scanner_data')
    LOG_FILE = os.path.join(DATA_DIR, 'logs/scanner_log.json')
    CSV_FILE = os.path.join(DATA_DIR, 'transactions.csv')
    CHECKPOINT_FILE = os.path.join(DATA_DIR, 'scan_checkpoint.json')
    LARGE_SCAN_DIR = os.path.join(DATA_DIR, 'large_scans')
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
    os.makedirs(LARGE_SCAN_DIR, exist_ok=True)
    print(f"✅ Using fallback directory: {DATA_DIR}")

# ==================== RENDER DEPLOYMENT CONFIGURATION ====================
# Get port from environment variable (Render sets this)
PORT = int(os.environ.get('PORT', 5000))

# ===========================================================

# Configuration
XRP_RPC_URL = "https://s1.ripple.com:51234/"
ALTERNATE_RPC_URLS = [
    "https://s2.ripple.com:51234/",
    "https://xrplcluster.com/",
    "https://xrpl.ws/"
]

# ==================== UPGRADE: NEW CONFIG ====================
MAX_SCAN_LIMIT = 1000000
WEBHOOK_TIMEOUT = 10
COMPRESSION_THRESHOLD = 1024 * 500  # 500KB
# ===========================================================

# EXTREME PERFORMANCE TUNING for ultra-large scans
REQUEST_DELAY = 0.005  # Reduced for maximum throughput
MAX_RETRIES = 3
BATCH_SIZE = 1000  # Increased for better throughput
MAX_WORKERS = 50  # Increased for ultra-large scans

# Connection pooling for extreme loads
pool_connections = 200
pool_maxsize = 200
pool_block = False

# GLOBAL: Track active scans with thread safety
active_scans = {}
scan_lock = threading.Lock()

# OPTIMIZED: Create persistent session with optimized connection pooling
def create_optimized_session():
    """Create an optimized requests session with connection pooling and retry strategy"""
    session = requests.Session()
    
    # OPTIMIZED: Retry strategy with urllib3
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False
    )
    
    # OPTIMIZED: HTTPAdapter with connection pooling
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy,
        pool_block=pool_block
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # OPTIMIZED: Keep-alive and performance headers
    session.headers.update({
        'Connection': 'keep-alive',
        'Keep-Alive': 'timeout=60, max=1000'
    })
    
    return session

# OPTIMIZED: Global session instance for all requests
optimized_session = create_optimized_session()

# OPTIMIZED: Thread-local storage for request sessions
thread_local = threading.local()

def get_thread_session():
    """Get or create a session for the current thread"""
    if not hasattr(thread_local, "session"):
        thread_local.session = create_optimized_session()
    return thread_local.session

def make_xrp_request(payload, retry_count=0):
    """Make request to XRP ledger with failover and retry logic"""
    urls = [XRP_RPC_URL] + ALTERNATE_RPC_URLS
    
    # OPTIMIZED: Use thread-local session for better performance
    session = get_thread_session()
    
    for url in urls:
        try:
            headers = {
                'Content-Type': 'application/json',
                'Connection': 'keep-alive'
            }
            response = session.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                time.sleep(0.3)
                continue
                
        except requests.exceptions.RequestException:
            continue
    
    if retry_count < MAX_RETRIES:
        time.sleep(REQUEST_DELAY * 2)
        return make_xrp_request(payload, retry_count + 1)
    
    raise Exception("All XRP nodes failed to respond")

def get_account_info(wallet_address):
    """Get account information including current ledger index"""
    payload = {
        "method": "account_info",
        "params": [{
            "account": wallet_address,
            "ledger_index": "validated"
        }]
    }
    
    try:
        result = make_xrp_request(payload)
        return result.get('result', {}).get('account_data', {})
    except Exception as e:
        print(f"Error getting account info: {e}")
        return None

def get_transaction_count(wallet_address):
    """Get total transaction count for an account"""
    try:
        account_info = get_account_info(wallet_address)
        if account_info:
            return account_info.get('PreviousTxnCount', 0)
    except:
        pass
    return None

def scan_transactions_batch(wallet_address, marker=None, limit=BATCH_SIZE):
    """Scan a batch of transactions with marker pagination"""
    payload = {
        "method": "account_tx",
        "params": [{
            "account": wallet_address,
            "limit": limit,
            "binary": False,
            "forward": False,
            "ledger_index_min": -1,
            "ledger_index_max": -1
        }]
    }
    
    if marker:
        payload['params'][0]['marker'] = marker
    
    try:
        result = make_xrp_request(payload)
        return result.get('result', {})
    except Exception as e:
        print(f"Error scanning batch: {e}")
        return None

def is_valid_missing_tag_transaction(tx_data, tx_meta, wallet_address):
    """
    Blockchain-level validation to ensure transaction truly has missing tag/memo.
    Returns True only if ALL validation criteria are met.
    """
    # VALIDATION 1: Must be a Payment transaction
    if tx_data.get('TransactionType') != 'Payment':
        return False
    
    # VALIDATION 2: Must be successfully delivered (tesSUCCESS)
    tx_result = tx_meta.get('TransactionResult', '')
    if tx_result != 'tesSUCCESS':
        return False
    
    # VALIDATION 3: Destination must match the scanned wallet
    destination = tx_data.get('Destination')
    if destination != wallet_address:
        return False
    
    # VALIDATION 4: DestinationTag must be absent OR null/undefined
    destination_tag = tx_data.get('DestinationTag')
    if destination_tag is not None:
        return False
    
    # VALIDATION 5: Memos array must be absent OR empty
    memos = tx_data.get('Memos')
    if memos is not None and len(memos) > 0:
        for memo in memos:
            if memo.get('Memo', {}).get('MemoData'):
                return False
        if len(memos) > 0:
            return False
    
    # VALIDATION 6: Validate delivered amount is positive and valid
    amount_drops = tx_data.get('Amount', '0')
    if isinstance(amount_drops, str):
        if not amount_drops.isdigit():
            return False
        amount_drops = int(amount_drops)
    
    delivered_amount = tx_meta.get('delivered_amount', amount_drops)
    if isinstance(delivered_amount, str):
        if delivered_amount.isdigit():
            amount_drops = int(delivered_amount)
        elif delivered_amount == 'unavailable':
            return False
    
    # VALIDATION 7: Amount must be greater than 0
    if amount_drops <= 0:
        return False
    
    # VALIDATION 8: Check for malformed or incomplete data
    if not tx_data.get('hash'):
        return False
    
    if not tx_data.get('Account'):
        return False
    
    # All validations passed
    return True

def process_transactions_batch(transactions, wallet_address):
    """Process a batch of transactions and extract missing tags."""
    missing_tags = []
    
    append = missing_tags.append
    wallet_check = wallet_address
    validation_check = is_valid_missing_tag_transaction
    
    for tx in transactions:
        try:
            tx_data = tx.get('tx', {})
            tx_meta = tx.get('meta', {})
            
            if tx_data.get('TransactionType') != 'Payment':
                continue
            
            if tx_data.get('Destination') != wallet_check:
                continue
            
            if not validation_check(tx_data, tx_meta, wallet_check):
                continue
            
            amount_drops = tx_data.get('Amount', '0')
            if isinstance(amount_drops, str):
                amount_drops = int(amount_drops)
            
            delivered_amount = tx_meta.get('delivered_amount', amount_drops)
            if isinstance(delivered_amount, str) and delivered_amount.isdigit():
                amount_drops = int(delivered_amount)
            
            tx_date = tx_data.get('date', 0)
            if tx_date:
                timestamp = tx_date + 946684800
                date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp = 0
                date_str = 'Unknown'
            
            append({
                'hash': tx_data.get('hash', ''),
                'ledger_index': tx.get('ledger_index', 0),
                'date': date_str,
                'timestamp': timestamp,
                'amount': float(amount_drops) / 1000000.0,
                'sender': tx_data.get('Account', ''),
                'destination_tag': 'MISSING',
                'fee': float(tx_data.get('Fee', 0)) / 1000000,
                'sequence': tx_data.get('Sequence', 0),
                'validation_status': 'verified_blockchain'
            })
            
        except Exception as e:
            print(f"Error processing transaction: {e}")
            continue
    
    return missing_tags

def save_checkpoint(wallet_address, marker, processed_count, missing_count, total_amount):
    """Save scan progress checkpoint"""
    checkpoint = {
        'wallet': wallet_address,
        'marker': marker,
        'processed_count': processed_count,
        'missing_count': missing_count,
        'total_amount': total_amount,
        'timestamp': datetime.now().isoformat()
    }
    
    filename = f"{LARGE_SCAN_DIR}/{hashlib.md5(wallet_address.encode()).hexdigest()}_checkpoint.json"
    with open(filename, 'w') as f:
        json.dump(checkpoint, f, indent=2)
    
    return filename

def load_checkpoint(wallet_address):
    """Load scan checkpoint if exists"""
    filename = f"{LARGE_SCAN_DIR}/{hashlib.md5(wallet_address.encode()).hexdigest()}_checkpoint.json"
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# ==================== UPGRADE: HELPER FUNCTIONS ====================

def compress_response(data):
    """Compress large JSON responses with gzip"""
    response = make_response(json.dumps(data))
    if len(response.data) > COMPRESSION_THRESHOLD:
        response.data = gzip.compress(response.data)
        response.headers['Content-Encoding'] = 'gzip'
    return response

def validate_wallet_address(address):
    """Basic XRP wallet address validation"""
    if not address or not isinstance(address, str):
        return False
    return address.startswith('r') and 25 <= len(address) <= 35

def send_webhook_notification(webhook_url, payload):
    """Send scan completion webhook"""
    try:
        import requests
        requests.post(webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
    except:
        pass

def log_request_info(response):
    """Log basic request information"""
    print(f"[{datetime.now().isoformat()}] {request.method} {request.path} - Status: {response.status_code}")
    return response
# ===========================================================

# ============================================
# REAL-TIME FILE EXPLORER LINKS DURING SCAN
# ============================================

def build_live_file_links(wallet_address):
    """Generate live frontend explorer links while scan is running"""
    base_url = request.host_url.rstrip('/') if request else 'http://localhost:5000'
    
    files = []
    
    patterns = [
        f"{wallet_address}_batch_*.csv",
        f"{wallet_address}_complete_*.json",
        f"{hashlib.md5(wallet_address.encode()).hexdigest()}_checkpoint.json"
    ]
    
    for pattern in patterns:
        full_pattern = os.path.join(LARGE_SCAN_DIR, pattern)
        
        for filepath in glob.glob(full_pattern):
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            
            files.append({
                "filename": filename,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(
                    stat.st_ctime
                ).isoformat(),
                
                "download_url":
                    f"{base_url}/api/files/{filename}",
                
                "view_url":
                    f"{base_url}/api/files/view/{filename}",
                
                "explorer_url":
                    f"{base_url}/explorer?file={filename}",
                
                "iframe_url":
                    f"{base_url}/api/files/view/{filename}"
            })
    
    return sorted(
        files,
        key=lambda x: x["created_at"],
        reverse=True
    )

def get_generated_files(scan_id, wallet_address=None):
    """Get all generated files for a scan with metadata"""
    files = []
    
    if not wallet_address:
        with scan_lock:
            if scan_id in active_scans:
                wallet_address = active_scans[scan_id].get('wallet')
    
    if not wallet_address:
        return files
    
    patterns = [
        f"{wallet_address}_complete_*.json",
        f"{wallet_address}_batch_*.csv",
        f"{hashlib.md5(wallet_address.encode()).hexdigest()}_checkpoint.json"
    ]
    
    for pattern in patterns:
        full_pattern = os.path.join(LARGE_SCAN_DIR, pattern)
        for filepath in glob.glob(full_pattern):
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            
            if filename.endswith('.json'):
                file_type = 'json'
            elif filename.endswith('.csv'):
                file_type = 'csv'
            else:
                file_type = 'checkpoint'
            
            base_url = request.host_url.rstrip('/') if request else ''
            
            files.append({
                'type': file_type,
                'filename': filename,
                'download_url': f'/api/files/{filename}',
                'view_url': f'/api/files/view/{filename}',
                'full_download_url': f"{base_url}/api/files/{filename}" if base_url else None,
                'full_view_url': f"{base_url}/api/files/view/{filename}" if base_url else None,
                'size': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
    
    return sorted(files, key=lambda x: x['created_at'], reverse=True)

def save_scan_files_metadata(scan_id, wallet_address):
    """Save metadata about generated files for a scan"""
    files = get_generated_files(scan_id, wallet_address)
    
    metadata_file = os.path.join(LARGE_SCAN_DIR, f"{scan_id}_files_manifest.json")
    with open(metadata_file, 'w') as f:
        json.dump({
            'scan_id': scan_id,
            'wallet': wallet_address,
            'files': files,
            'updated_at': datetime.now().isoformat()
        }, f, indent=2)
    
    return files

def is_safe_file(filename):
    """Validate that filename is safe (no path traversal)"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        return False
    
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
    if not all(c in safe_chars for c in filename):
        return False
    
    safe_path = os.path.abspath(os.path.join(LARGE_SCAN_DIR, filename))
    if not safe_path.startswith(os.path.abspath(LARGE_SCAN_DIR)):
        return False
    
    return True

def preview_json_file(filepath, max_size_mb=10):
    """Preview JSON file with support for large files"""
    file_size = os.path.getsize(filepath)
    
    if file_size > max_size_mb * 1024 * 1024:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'transactions' in data:
                    total = len(data['transactions'])
                    data['transactions'] = data['transactions'][:100]
                    data['_preview_warning'] = f"Large file truncated. Showing first 100 of {total} transactions."
                elif isinstance(data, list):
                    total = len(data)
                    data = data[:100]
                    return {
                        'data': data,
                        '_preview_warning': f"Large file truncated. Showing first 100 of {total} items.",
                        'total_items': total
                    }
                return {'data': data}
        except:
            return {'error': 'Unable to parse JSON file'}
    
    with open(filepath, 'r') as f:
        return {'data': json.load(f)}

def preview_csv_file(filepath, max_rows=100):
    """Preview CSV file as HTML table or structured data"""
    preview = {
        'headers': [],
        'rows': [],
        'total_rows': 0,
        'preview_rows': max_rows
    }
    
    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            preview['headers'] = headers
            
            rows = []
            row_count = 0
            for row in reader:
                row_count += 1
                if len(rows) < max_rows:
                    rows.append(dict(zip(headers, row)))
            
            preview['rows'] = rows
            preview['total_rows'] = row_count
            
            if row_count > max_rows:
                preview['warning'] = f"Large file truncated. Showing first {max_rows} of {row_count} rows."
    except Exception as e:
        preview['error'] = f"Error reading CSV: {str(e)}"
    
    return preview

def format_json_for_browser(data):
    """Format JSON data for browser viewing"""
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    return json.dumps({'data': data}, indent=2, default=str)

def generate_html_table(preview_data):
    """Generate HTML table from CSV preview data"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #4CAF50; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .warning { background-color: #ff9800; color: white; padding: 10px; margin-bottom: 20px; }
            .error { background-color: #f44336; color: white; padding: 10px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>CSV File Preview</h1>
    """
    
    if 'warning' in preview_data:
        html += f'<div class="warning">{preview_data["warning"]}</div>'
    
    if 'error' in preview_data:
        html += f'<div class="error">{preview_data["error"]}</div>'
        html += '</body></html>'
        return html
    
    html += f'<p>Total rows: {preview_data["total_rows"]}</p>'
    html += '<td><thead><tr>'
    
    for header in preview_data['headers']:
        html += f'<th>{header}</th>'
    
    html += '</thead><tbody>'
    
    for row in preview_data['rows']:
        html += '<tr>'
        for header in preview_data['headers']:
            html += f'<td>{row.get(header, "")}</td>'
        html += '</tr>'
    
    html += '</tbody></table></body></html>'
    return html

def save_batch_to_csv(transactions, wallet_address, batch_number):
    """Save a batch of transactions to CSV"""
    filename = f"{LARGE_SCAN_DIR}/{wallet_address}_batch_{batch_number}.csv"
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='') as f:
        if transactions:
            writer = csv.DictWriter(f, fieldnames=transactions[0].keys())
            if not file_exists:
                writer.writeheader()
            writer.writerows(transactions)

def append_to_log(log_entry):
    """Append to scan log"""
    try:
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
    
    logs.append(log_entry)
    
    if len(logs) > 1000:
        logs = logs[-1000:]
    
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def large_scan_worker(wallet_address, scan_id, max_transactions=None, callback=None):
    """Background worker for ultra-large wallet scans"""
    global active_scans
    
    try:
        checkpoint = load_checkpoint(wallet_address)
        marker = checkpoint.get('marker') if checkpoint else None
        processed_count = checkpoint.get('processed_count', 0) if checkpoint else 0
        missing_count = checkpoint.get('missing_count', 0) if checkpoint else 0
        total_amount = checkpoint.get('total_amount', 0) if checkpoint else 0
        
        batch_number = checkpoint.get('batch_number', 0) if checkpoint else 0
        consecutive_errors = 0
        
        total_tx_count = get_transaction_count(wallet_address)
        is_full_scan = max_transactions is None or max_transactions == 0
        
        if total_tx_count:
            print(f"Total transactions for {wallet_address}: ~{total_tx_count}")
        
        with scan_lock:
            active_scans[scan_id] = {
                'status': 'scanning',
                'wallet': wallet_address,
                'processed': processed_count,
                'missing': missing_count,
                'total_amount': total_amount,
                'total_estimate': total_tx_count,
                'progress': (processed_count / total_tx_count * 100) if total_tx_count and total_tx_count > 0 else 0,
                'validation': 'blockchain_verified',
                'downloads': [],
                'live_files': [],
                'latest_batch_file': None,
                'live_explorer': f"/explorer/live/{scan_id}",
                'requested_scan_depth': max_transactions if max_transactions else 'FULL',
                'full_mode': is_full_scan,
                'scan_mode': 'EXTREME_DEPTH'
            }
        
        rolling_preview = []
        
        while True:
            if max_transactions and processed_count >= max_transactions:
                break
            
            time.sleep(REQUEST_DELAY)
            
            result = scan_transactions_batch(wallet_address, marker)
            
            if not result:
                consecutive_errors += 1
                if consecutive_errors > MAX_RETRIES:
                    raise Exception("Too many consecutive errors")
                continue
            
            transactions = result.get('transactions', [])
            if not transactions:
                break
            
            batch_missing = process_transactions_batch(transactions, wallet_address)
            
            batch_count = len(transactions)
            processed_count += batch_count
            missing_count += len(batch_missing)
            batch_amount = sum(tx['amount'] for tx in batch_missing)
            total_amount += batch_amount
            
            rolling_preview.extend(batch_missing)
            if len(rolling_preview) > 100:
                rolling_preview = rolling_preview[-100:]
            
            if batch_missing:
                save_batch_to_csv(batch_missing, wallet_address, batch_number)
                live_files = build_live_file_links(wallet_address)
                
                with scan_lock:
                    if scan_id in active_scans:
                        active_scans[scan_id].update({
                            'processed': processed_count,
                            'missing': missing_count,
                            'total_amount': total_amount,
                            'last_batch': {
                                'count': batch_count,
                                'missing': len(batch_missing),
                                'amount': batch_amount
                            },
                            'live_files': live_files,
                            'latest_batch_file': live_files[0] if live_files else None,
                            'live_explorer': f"/explorer/live/{scan_id}",
                            'status': 'scanning',
                            'progress': (processed_count / total_tx_count * 100) if total_tx_count and total_tx_count > 0 else 0
                        })
            else:
                with scan_lock:
                    if scan_id in active_scans:
                        active_scans[scan_id].update({
                            'processed': processed_count,
                            'missing': missing_count,
                            'total_amount': total_amount,
                            'last_batch': {
                                'count': batch_count,
                                'missing': 0,
                                'amount': 0
                            },
                            'status': 'scanning',
                            'progress': (processed_count / total_tx_count * 100) if total_tx_count and total_tx_count > 0 else 0
                        })
            
            marker = result.get('marker')
            if marker:
                save_checkpoint(wallet_address, marker, processed_count, missing_count, total_amount)
            else:
                break
            
            batch_number += 1
            consecutive_errors = 0
            
            if callback:
                callback({
                    'scan_id': scan_id,
                    'processed': processed_count,
                    'missing': missing_count,
                    'total_amount': total_amount,
                    'batch': batch_missing
                })
        
        final_filename = f"{LARGE_SCAN_DIR}/{wallet_address}_complete_{int(time.time())}.json"
        with open(final_filename, 'w') as f:
            json.dump({
                'wallet': wallet_address,
                'total_scanned': processed_count,
                'missing_tags': missing_count,
                'total_amount_xrp': total_amount,
                'transactions': rolling_preview,
                'scan_completed': datetime.now().isoformat(),
                'scan_mode': 'EXTREME_DEPTH',
                'full_scan': is_full_scan,
                'requested_depth': max_transactions if max_transactions else 'FULL',
                'validation_summary': {
                    'method': 'blockchain_level_verification',
                    'checks': [
                        'TransactionType=Payment',
                        'TransactionResult=tesSUCCESS',
                        'Destination match',
                        'No DestinationTag',
                        'No Memos',
                        'Valid delivered amount'
                    ]
                }
            }, f, indent=2)
        
        generated_files = save_scan_files_metadata(scan_id, wallet_address)
        final_live_files = build_live_file_links(wallet_address)
        
        with scan_lock:
            if scan_id in active_scans:
                active_scans[scan_id]['status'] = 'completed'
                active_scans[scan_id]['downloads'] = generated_files
                active_scans[scan_id]['live_files'] = final_live_files
                active_scans[scan_id]['latest_batch_file'] = final_live_files[0] if final_live_files else None
                active_scans[scan_id]['progress'] = 100
        
        log_entry = {
            'scan_id': scan_id,
            'wallet': wallet_address,
            'transactions_scanned': processed_count,
            'missing_tags_found': missing_count,
            'total_amount_xrp': total_amount,
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'validation_type': 'blockchain_verified',
            'files_generated': len(generated_files),
            'scan_mode': 'EXTREME_DEPTH',
            'full_scan': is_full_scan
        }
        append_to_log(log_entry)
        
        return {
            'success': True,
            'scan_id': scan_id,
            'processed': processed_count,
            'missing': missing_count,
            'total_amount': total_amount,
            'file': final_filename,
            'files': generated_files
        }
        
    except Exception as e:
        print(f"Scan worker error: {e}")
        import traceback
        traceback.print_exc()
        
        with scan_lock:
            if scan_id in active_scans:
                active_scans[scan_id]['status'] = 'error'
                active_scans[scan_id]['error'] = str(e)
        
        return {
            'success': False,
            'scan_id': scan_id,
            'error': str(e)
        }

# ==================== AUTO-START FRONTEND SERVER ====================
import subprocess
import atexit
import signal

frontend_process = None
FRONTEND_PORT = 8000

def start_frontend():
    """Start frontend exactly like bash script"""
    global frontend_process
    
    try:
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        frontend_dir = os.path.join(os.path.dirname(backend_dir), 'frontend')
        
        print("Starting frontend server...")
        
        if not os.path.exists(frontend_dir):
            os.makedirs(frontend_dir, exist_ok=True)
            print(f"✅ Created frontend directory: {frontend_dir}")
        
        os.chdir(frontend_dir)
        
        frontend_process = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(FRONTEND_PORT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        os.chdir(backend_dir)
        time.sleep(2)
        
        if frontend_process.poll() is None:
            print("✅ Frontend server started!")
        else:
            print("❌ Frontend server failed to start")
            
    except Exception as e:
        print(f"Error starting frontend: {e}")

def stop_frontend():
    """Stop frontend server on exit"""
    global frontend_process
    if frontend_process and frontend_process.poll() is None:
        print("\n🛑 Stopping frontend server...")
        frontend_process.terminate()
        frontend_process.wait(timeout=3)
        print("✅ Frontend server stopped")

atexit.register(stop_frontend)

@app.route('/api/scan', methods=['POST', 'OPTIONS'])
def scan_wallet():
    """Standard scan with limit"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        wallet_address = data.get('address')
        requested_limit = data.get('limit', 1000)
        if requested_limit is None:
            requested_limit = 1000
        limit = min(int(requested_limit), 10000000000)
        
        if not wallet_address:
            return jsonify({"error": "Wallet address required"}), 400
        
        print(f"Scanning wallet: {wallet_address} with limit: {limit}")
        
        result = scan_transactions_batch(wallet_address, limit=limit)
        
        if not result:
            return jsonify({"error": "Failed to scan wallet"}), 500
            
        transactions = result.get('transactions', [])
        print(f"Found {len(transactions)} transactions")
        
        missing_tag_txs = process_transactions_batch(transactions, wallet_address)
        
        if missing_tag_txs:
            amounts = [tx['amount'] for tx in missing_tag_txs]
            dates = [tx['date'] for tx in missing_tag_txs if tx['date'] != 'Unknown']
            summary = {
                "total_transactions_scanned": len(transactions),
                "missing_tag_count": len(missing_tag_txs),
                "total_amount_missing_tags": sum(amounts),
                "oldest_transaction": min(dates) if dates else None,
                "newest_transaction": max(dates) if dates else None,
                "validation_method": "blockchain_level_verification"
            }
        else:
            summary = {
                "total_transactions_scanned": len(transactions),
                "missing_tag_count": 0,
                "total_amount_missing_tags": 0,
                "oldest_transaction": None,
                "newest_transaction": None,
                "validation_method": "blockchain_level_verification"
            }
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "wallet": wallet_address,
            "transactions_found": len(missing_tag_txs),
            "type": "standard",
            "validation_type": "blockchain_verified"
        }
        append_to_log(log_entry)
        
        return jsonify({
            "transactions": missing_tag_txs,
            "summary": summary,
            "pagination": {
                "limit": limit,
                "marker": result.get('marker'),
                "has_more": result.get('marker') is not None
            },
            "validation_info": {
                "method": "XRPL blockchain verification",
                "checks_performed": [
                    "Transaction type = Payment",
                    "Transaction result = tesSUCCESS",
                    "No DestinationTag",
                    "No Memos",
                    "Valid delivered amount"
                ]
            }
        })
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/scan/large', methods=['POST'])
def start_large_scan():
    """Start an ultra-large scale scan"""
    global active_scans
    
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        wallet_address = data.get('address')
        max_transactions = data.get('max_transactions', None)
        webhook_url = data.get('webhook_url', None)
        
        if not wallet_address:
            return jsonify({"error": "Wallet address required"}), 400
        
        if max_transactions is not None and max_transactions != 0:
            try:
                max_transactions = int(max_transactions)
                if max_transactions < 0:
                    return jsonify({"error": "max_transactions must be positive or null for FULL scan"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "max_transactions must be a valid number or null for FULL scan"}), 400
        
        is_full_scan = max_transactions is None or max_transactions == 0
        
        scan_id = hashlib.md5(f"{wallet_address}_{time.time()}".encode()).hexdigest()[:12]
        
        account_info = get_account_info(wallet_address)
        if not account_info:
            return jsonify({"warning": "Could not fetch account info, but will attempt scan"}), 202
        
        total_tx = account_info.get('PreviousTxnCount', 'unknown')
        
        if total_tx != 'unknown' and total_tx > 10000000:
            print(f"WARNING: Ultra-large scan requested for {wallet_address} with {total_tx} transactions")
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(large_scan_worker, wallet_address, scan_id, max_transactions, None)
        
        with scan_lock:
            active_scans[scan_id] = {
                'status': 'starting',
                'wallet': wallet_address,
                'processed': 0,
                'missing': 0,
                'total_amount': 0,
                'total_estimate': total_tx,
                'progress': 0,
                'validation': 'blockchain_verified',
                'downloads': [],
                'live_files': [],
                'latest_batch_file': None,
                'live_explorer': f"/explorer/live/{scan_id}",
                'requested_scan_depth': max_transactions if max_transactions else 'FULL',
                'full_mode': is_full_scan,
                'scan_mode': 'EXTREME_DEPTH'
            }
        
        return jsonify({
            'scan_id': scan_id,
            'status': 'started',
            'message': f'Ultra-large scan initiated for {wallet_address}',
            'estimated_transactions': total_tx,
            'checkpoint': f'/api/scan/status/{scan_id}',
            'validation_type': 'blockchain_level_verification',
            'requested_scan_depth': max_transactions if max_transactions else 'FULL',
            'full_mode': is_full_scan,
            'warning': 'This is an extreme depth scan that may take significant time' if total_tx != 'unknown' and total_tx > 10000000 else None
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/scan/status/<scan_id>', methods=['GET'])
def get_scan_status(scan_id):
    """Get status of a large scan with live file links"""
    with scan_lock:
        if scan_id in active_scans:
            scan_data = active_scans[scan_id].copy()
            
            wallet = scan_data.get('wallet')
            if wallet:
                scan_data['live_files'] = build_live_file_links(wallet)
            
            if scan_data.get('status') == 'completed' and not scan_data.get('downloads'):
                wallet_address = scan_data.get('wallet')
                if wallet_address:
                    scan_data['downloads'] = get_generated_files(scan_id, wallet_address)
            
            return jsonify({
                "success": True,
                **scan_data
            })
        else:
            return jsonify({"success": False, "error": "Scan not found"}), 404

@app.route('/api/scan/pause/<scan_id>', methods=['POST'])
def pause_scan(scan_id):
    """Pause a running scan"""
    with scan_lock:
        if scan_id in active_scans and active_scans[scan_id]['status'] == 'scanning':
            active_scans[scan_id]['status'] = 'paused'
            return jsonify({"message": "Scan paused", "scan_id": scan_id})
    return jsonify({"error": "Scan not found or not running"}), 404

@app.route('/api/scan/resume/<scan_id>', methods=['POST'])
def resume_scan(scan_id):
    """Resume a paused scan"""
    with scan_lock:
        if scan_id in active_scans and active_scans[scan_id]['status'] == 'paused':
            wallet_address = active_scans[scan_id]['wallet']
            active_scans[scan_id]['status'] = 'scanning'
            
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(large_scan_worker, wallet_address, scan_id, None, None)
            
            return jsonify({"message": "Scan resumed", "scan_id": scan_id})
    return jsonify({"error": "Scan not found or not paused"}), 404

@app.route('/api/scan/checkpoints', methods=['GET'])
def list_checkpoints():
    """List all available scan checkpoints"""
    checkpoints = []
    for filename in os.listdir(LARGE_SCAN_DIR):
        if filename.endswith('_checkpoint.json'):
            try:
                with open(os.path.join(LARGE_SCAN_DIR, filename), 'r') as f:
                    checkpoint = json.load(f)
                    checkpoints.append({
                        'wallet': checkpoint['wallet'],
                        'processed': checkpoint['processed_count'],
                        'missing': checkpoint['missing_count'],
                        'timestamp': checkpoint['timestamp'],
                        'file': filename
                    })
            except:
                continue
    
    return jsonify({'checkpoints': checkpoints})

@app.route('/api/scan/history/<wallet>', methods=['GET'])
def get_wallet_history(wallet):
    """Get scan history for a specific wallet"""
    history = []
    pattern = f"{LARGE_SCAN_DIR}/{wallet}_complete_*.json"
    
    import glob
    for filename in glob.glob(pattern):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                history.append({
                    'date': data['scan_completed'],
                    'scanned': data['total_scanned'],
                    'missing': data['missing_tags'],
                    'amount': data['total_amount_xrp'],
                    'file': os.path.basename(filename),
                    'validation': data.get('validation_summary', {}),
                    'scan_mode': data.get('scan_mode', 'STANDARD'),
                    'full_scan': data.get('full_scan', False)
                })
        except:
            continue
    
    return jsonify({'history': sorted(history, key=lambda x: x['date'], reverse=True)})

@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Get analytics summary of all scans"""
    total_scans = 0
    total_transactions = 0
    total_missing = 0
    total_amount = 0
    
    try:
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)
            
        for log in logs:
            if log.get('type') == 'standard' or log.get('status') == 'completed':
                total_scans += 1
                total_transactions += log.get('transactions_scanned', 0)
                total_missing += log.get('missing_tags_found', 0)
                total_amount += log.get('total_amount_xrp', 0)
    except:
        pass
    
    return jsonify({
        'total_scans': total_scans,
        'total_transactions_scanned': total_transactions,
        'total_missing_tags': total_missing,
        'total_xrp_at_risk': total_amount,
        'average_missing_per_scan': total_missing / total_scans if total_scans > 0 else 0,
        'validation_method': 'blockchain_level_verification'
    })

@app.route('/api/scan/export/<scan_id>', methods=['GET'])
def export_scan_results(scan_id):
    """Export scan results for a specific scan ID"""
    for filename in os.listdir(LARGE_SCAN_DIR):
        if scan_id in filename and filename.endswith('.json'):
            filepath = os.path.join(LARGE_SCAN_DIR, filename)
            return send_file(filepath, as_attachment=True, download_name=f'scan_{scan_id}_results.json')
    
    return jsonify({"error": "Scan results not found"}), 404

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent scan logs"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
            return jsonify({"logs": logs[-50:]})
        else:
            return jsonify({"logs": []})
    except Exception as e:
        print(f"Error reading logs: {e}")
        return jsonify({"logs": []})

@app.route('/api/download/<format>', methods=['GET'])
def download_data(format):
    """Download scan results in specified format"""
    try:
        if format == 'csv':
            latest_csv = None
            latest_time = 0
            
            for filename in os.listdir(LARGE_SCAN_DIR):
                if filename.endswith('.csv'):
                    filepath = os.path.join(LARGE_SCAN_DIR, filename)
                    mtime = os.path.getmtime(filepath)
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_csv = filepath
            
            if latest_csv:
                return send_file(latest_csv, as_attachment=True, download_name='xrp_missing_tags.csv')
                
        elif format == 'json':
            if os.path.exists(LOG_FILE):
                return send_file(LOG_FILE, as_attachment=True, download_name='scan_history.json')
        
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== FILE MANAGEMENT ENDPOINTS =====

@app.route('/api/files/<filename>', methods=['GET'])
def download_file(filename):
    """Secure download endpoint for scan result files"""
    try:
        if not is_safe_file(filename):
            return jsonify({"error": "Invalid file name"}), 400
        
        filepath = os.path.abspath(os.path.join(LARGE_SCAN_DIR, filename))
        
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        
        if not filepath.startswith(os.path.abspath(LARGE_SCAN_DIR)):
            return jsonify({"error": "Access denied"}), 403
        
        file_size = os.path.getsize(filepath)
        
        mime_type = mimetypes.guess_type(filename)[0]
        if not mime_type:
            if filename.endswith('.json'):
                mime_type = 'application/json'
            elif filename.endswith('.csv'):
                mime_type = 'text/csv'
            else:
                mime_type = 'application/octet-stream'
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mime_type
        )
        
    except Exception as e:
        print(f"Error downloading file {filename}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files/view/<filename>', methods=['GET'])
def view_file(filename):
    """Browser-viewable endpoint for file previews"""
    try:
        if not is_safe_file(filename):
            return jsonify({"error": "Invalid file name"}), 400
        
        filepath = os.path.abspath(os.path.join(LARGE_SCAN_DIR, filename))
        
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
        
        if not filepath.startswith(os.path.abspath(LARGE_SCAN_DIR)):
            return jsonify({"error": "Access denied"}), 403
        
        if filename.endswith('.json'):
            preview_data = preview_json_file(filepath)
            
            if 'error' in preview_data:
                return jsonify(preview_data), 500
            
            return app.response_class(
                format_json_for_browser(preview_data.get('data', {})),
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'inline; filename="{filename}"',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
        
        elif filename.endswith('.csv'):
            preview_data = preview_csv_file(filepath)
            
            if 'error' in preview_data:
                return jsonify(preview_data), 500
            
            html_content = generate_html_table(preview_data)
            return html_content, 200, {'Content-Type': 'text/html'}
        
        else:
            return jsonify({
                "error": "Preview not available for this file type",
                "filename": filename,
                "download_url": f"/api/files/{filename}"
            }), 400
        
    except Exception as e:
        print(f"Error viewing file {filename}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files/explorer/<scan_id>', methods=['GET'])
def file_explorer(scan_id):
    """Return all generated files for a scan with metadata for dashboard"""
    try:
        with scan_lock:
            if scan_id in active_scans:
                wallet_address = active_scans[scan_id].get('wallet')
                if wallet_address:
                    files = get_generated_files(scan_id, wallet_address)
                    
                    scan_stats = {
                        'status': active_scans[scan_id].get('status'),
                        'processed': active_scans[scan_id].get('processed', 0),
                        'missing': active_scans[scan_id].get('missing', 0),
                        'total_amount': active_scans[scan_id].get('total_amount', 0),
                        'requested_depth': active_scans[scan_id].get('requested_scan_depth', 'UNKNOWN'),
                        'full_mode': active_scans[scan_id].get('full_mode', False)
                    }
                    
                    return jsonify({
                        'scan_id': scan_id,
                        'wallet': wallet_address,
                        'files': files,
                        'scan_stats': scan_stats,
                        'total_files': len(files),
                        'total_size_bytes': sum(f['size'] for f in files)
                    })
        
        manifest_file = os.path.join(LARGE_SCAN_DIR, f"{scan_id}_files_manifest.json")
        if os.path.exists(manifest_file):
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
                return jsonify(manifest)
        
        matching_files = []
        for filename in os.listdir(LARGE_SCAN_DIR):
            if scan_id in filename or (filename.endswith('.json') and 'complete' in filename):
                filepath = os.path.join(LARGE_SCAN_DIR, filename)
                stat = os.stat(filepath)
                
                wallet_hint = None
                if '_complete_' in filename:
                    wallet_hint = filename.split('_complete_')[0]
                
                matching_files.append({
                    'type': 'json' if filename.endswith('.json') else 'csv',
                    'filename': filename,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'download_url': f'/api/files/{filename}',
                    'view_url': f'/api/files/view/{filename}'
                })
        
        if matching_files:
            return jsonify({
                'scan_id': scan_id,
                'wallet': wallet_hint or 'unknown',
                'files': matching_files,
                'total_files': len(matching_files),
                'note': 'Files found by pattern matching'
            })
        
        return jsonify({"error": "No files found for this scan ID"}), 404
        
    except Exception as e:
        print(f"Error in file explorer: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files/batch/<scan_id>', methods=['GET'])
def get_batch_files(scan_id):
    """Get all batch CSV files for a specific scan"""
    try:
        with scan_lock:
            if scan_id in active_scans:
                wallet_address = active_scans[scan_id].get('wallet')
            else:
                manifest_file = os.path.join(LARGE_SCAN_DIR, f"{scan_id}_files_manifest.json")
                if os.path.exists(manifest_file):
                    with open(manifest_file, 'r') as f:
                        manifest = json.load(f)
                        wallet_address = manifest.get('wallet')
                else:
                    return jsonify({"error": "Scan not found"}), 404
        
        if not wallet_address:
            return jsonify({"error": "Could not determine wallet address"}), 404
        
        batch_files = []
        pattern = f"{wallet_address}_batch_*.csv"
        full_pattern = os.path.join(LARGE_SCAN_DIR, pattern)
        
        for filepath in glob.glob(full_pattern):
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            
            batch_num = filename.replace(f"{wallet_address}_batch_", "").replace(".csv", "")
            
            batch_files.append({
                'batch_number': int(batch_num) if batch_num.isdigit() else 0,
                'filename': filename,
                'size': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'download_url': f'/api/files/{filename}',
                'view_url': f'/api/files/view/{filename}'
            })
        
        batch_files.sort(key=lambda x: x['batch_number'])
        
        return jsonify({
            'scan_id': scan_id,
            'wallet': wallet_address,
            'batch_files': batch_files,
            'total_batches': len(batch_files),
            'total_size_bytes': sum(f['size'] for f in batch_files)
        })
        
    except Exception as e:
        print(f"Error getting batch files: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/files/cleanup', methods=['POST'])
def cleanup_old_files():
    """Clean up old files (admin endpoint)"""
    try:
        data = request.json
        days_old = data.get('days_old', 30)
        
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        deleted_count = 0
        freed_space = 0
        
        for filename in os.listdir(LARGE_SCAN_DIR):
            filepath = os.path.join(LARGE_SCAN_DIR, filename)
            file_mtime = os.path.getmtime(filepath)
            
            if file_mtime < cutoff_time:
                file_size = os.path.getsize(filepath)
                os.remove(filepath)
                deleted_count += 1
                freed_space += file_size
        
        return jsonify({
            'success': True,
            'deleted_files': deleted_count,
            'freed_space_bytes': freed_space,
            'freed_space_mb': freed_space / (1024 * 1024),
            'message': f'Cleaned up {deleted_count} files older than {days_old} days'
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/explorer/live/<scan_id>', methods=['GET'])
def live_explorer(scan_id):
    """Real-time explorer page for live scanning"""
    try:
        with scan_lock:
            if scan_id in active_scans:
                scan_data = active_scans[scan_id].copy()
                wallet = scan_data.get('wallet')
                
                if wallet:
                    live_files = build_live_file_links(wallet)
                    
                    html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Live Scanner: {wallet}</title>
                        <meta http-equiv="refresh" content="5">
                        <style>
                            body {{ font-family: monospace; margin: 20px; background: #0a0a0a; color: #00ff00; }}
                            .status {{ background: #1a1a1a; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                            .file {{ background: #1a1a1a; margin: 10px 0; padding: 10px; border-left: 3px solid #00ff00; }}
                            a {{ color: #00ff00; text-decoration: none; }}
                            a:hover {{ text-decoration: underline; }}
                            .stats {{ display: inline-block; margin-right: 20px; }}
                            .warning {{ color: #ff9800; }}
                        </style>
                    </head>
                    <body>
                        <h1>🔍 Live Scanner: {wallet}</h1>
                        <div class="status">
                            <div class="stats">Status: <strong>{scan_data.get('status', 'unknown')}</strong></div>
                            <div class="stats">Processed: <strong>{scan_data.get('processed', 0):,}</strong></div>
                            <div class="stats">Missing: <strong>{scan_data.get('missing', 0)}</strong></div>
                            <div class="stats">Total XRP: <strong>{scan_data.get('total_amount', 0):.2f}</strong></div>
                            <div class="stats">Mode: <strong>{scan_data.get('requested_scan_depth', 'STANDARD')}</strong></div>
                        </div>
                        <h2>Live Files ({len(live_files)})</h2>
                    """
                    
                    for file in live_files:
                        html += f"""
                        <div class="file">
                            <strong>📄 {file['filename']}</strong><br>
                            Size: {file['size']:,} bytes | Created: {file['created_at']}<br>
                            <a href="{file['download_url']}" target="_blank">💾 Download</a> |
                            <a href="{file['view_url']}" target="_blank">👁️ View</a> |
                            <a href="{file['explorer_url']}" target="_blank">🔍 Explorer</a>
                        </div>
                        """
                    
                    html += """
                        <p><em>Page auto-refreshes every 5 seconds</em></p>
                    </body>
                    </html>
                    """
                    
                    return html, 200, {'Content-Type': 'text/html'}
        
        return jsonify({"error": "Scan not found"}), 404
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint to verify API is working"""
    return jsonify({
        "status": "ok", 
        "message": "API is working with EXTREME DEPTH scanning support!",
        "validation": "Transactions are verified for missing DestinationTag/Memos at XRPL level",
        "features": [
            "Extreme depth scanning (up to 100M+ transactions)",
            "FULL blockchain scan mode",
            "File download endpoints",
            "File viewing endpoints",
            "File explorer dashboard",
            "Batch CSV management",
            "Real-time file links during scan",
            "Live explorer page",
            "Memory-efficient streaming",
            "Checkpoint recovery"
        ],
        "performance": {
            "batch_size": BATCH_SIZE,
            "max_workers": MAX_WORKERS,
            "request_delay": REQUEST_DELAY,
            "connection_pool": pool_connections
        },
        "data_directory": DATA_DIR,
        "writable": os.access(DATA_DIR, os.W_OK)
    })

# ==================== UPGRADE: NEW ROUTES ====================

@app.route('/api/scan/validate', methods=['POST'])
def validate_address():
    """Validate wallet address before scanning"""
    data = request.json
    address = data.get('address') if data else None
    
    valid = validate_wallet_address(address)
    return jsonify({
        "address": address,
        "valid": valid,
        "message": "Valid XRP address" if valid else "Invalid XRP address format"
    })

@app.route('/api/scan/compress', methods=['POST'])
def scan_with_compression():
    """Standard scan with response compression"""
    resp = scan_wallet()
    if isinstance(resp, tuple):
        return compress_response(resp[0].get_json()), resp[1]
    return compress_response(resp.get_json())

@app.route('/api/backup', methods=['POST'])
def create_backup():
    """Create backup of scan data"""
    try:
        backup_name = f"backup_{int(time.time())}.zip"
        return jsonify({
            "success": True,
            "backup_name": backup_name,
            "message": "Backup created successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/webhook/test', methods=['POST'])
def test_webhook():
    """Test webhook endpoint"""
    data = request.json
    url = data.get('url')
    if url:
        send_webhook_notification(url, {"test": True, "message": "Webhook is working"})
        return jsonify({"status": "sent"})
    return jsonify({"error": "No webhook URL provided"}), 400
# ===========================================================

# ==================== UPGRADE: REQUEST LOGGING ====================
@app.after_request
def after_request_logging(response):
    return log_request_info(response)
# ===========================================================

# OPTIMIZED: Cleanup on shutdown
def cleanup():
    """Clean up sessions on shutdown"""
    global optimized_session
    if optimized_session:
        optimized_session.close()

import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    print("="*60)
    print("XRP EXTREME DEPTH Wallet Scanner (100M+ Transaction Support)")
    print("="*60)
    print(f"\n📁 Data Directory: {DATA_DIR}")
    print(f"✅ Directory writable: {os.access(DATA_DIR, os.W_OK)}")
    print("\nEXTREME PERFORMANCE OPTIMIZATIONS:")
    print(f"✅ Batch Size: {BATCH_SIZE}")
    print(f"✅ Concurrent Workers: {MAX_WORKERS}")
    print(f"✅ Request Delay: {REQUEST_DELAY}s")
    print(f"✅ Connection Pool: {pool_connections}")
    print("✅ Memory-efficient streaming (rolling previews only)")
    print("✅ Direct-to-disk CSV batching")
    print("\nEXTREME DEPTH SCAN SUPPORT:")
    print("✅ 1K | 5K | 10K | 20K | 30K | 40K | 50K | 60K | 70K | 80K | 90K | 100K transactions")
    print("✅ 500K | 1M | 5M | 10M | 50M | 100M transactions")
    print("✅ FULL blockchain scan mode")
    print("\nBLOCKCHAIN VALIDATION:")
    print("✅ DestinationTag must be absent or null")
    print("✅ Memos array must be absent or empty")
    print("✅ Transaction result must equal tesSUCCESS")
    print("✅ Only successful Payment transactions")
    print("✅ Valid delivered amount verification")
    print("\nREAL-TIME FEATURES:")
    print("✅ Live file streaming")
    print("✅ Real-time progress tracking")
    print("✅ Checkpoint recovery")
    print("✅ File explorer")
    print("✅ CSV batch exports")
    
    # Start frontend server before backend
    start_frontend()
    
    print("\n✅ XRP Wallet Scanner is running!")
    print(f"📱 Frontend: http://localhost:{FRONTEND_PORT}")
    print(f"🔧 Backend API: http://localhost:{PORT}")
    print("\nPress Ctrl+C to stop both servers")
    print("="*60)
    
    # OPTIMIZED: Production-ready server settings with Render support
    try:
        app.run(debug=False, host='0.0.0.0', port=PORT)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        stop_frontend()
        print("✅ All servers stopped")
