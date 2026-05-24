#!/usr/bin/env python3
"""
XRP Extreme Depth Scanner - Unified Backend with Frontend Serving
Blockchain-verified missing DestinationTag & Memo detection
Supports scans from 1K to 100M+ transactions and FULL blockchain scans
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
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
import gzip
from functools import wraps
from flask import make_response
import subprocess
import atexit
import signal

# ==================== CONFIGURATION ====================
app = Flask(__name__)
CORS(app)

# ==================== AUTO-DISCOVER DATA DIRECTORY ====================
def get_data_directory():
    """Auto-discover or create writable data directory"""
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

DATA_DIR = get_data_directory()
LOG_FILE = os.path.join(DATA_DIR, 'logs/scanner_log.json')
CSV_FILE = os.path.join(DATA_DIR, 'transactions.csv')
CHECKPOINT_FILE = os.path.join(DATA_DIR, 'scan_checkpoint.json')
LARGE_SCAN_DIR = os.path.join(DATA_DIR, 'large_scans')

try:
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
    os.makedirs(LARGE_SCAN_DIR, exist_ok=True)
    print(f"✅ Data directories created in: {DATA_DIR}")
except Exception as e:
    print(f"⚠️ Directory creation warning: {e}")
    DATA_DIR = os.path.join(os.getcwd(), 'xrp_scanner_data')
    LOG_FILE = os.path.join(DATA_DIR, 'logs/scanner_log.json')
    CSV_FILE = os.path.join(DATA_DIR, 'transactions.csv')
    CHECKPOINT_FILE = os.path.join(DATA_DIR, 'scan_checkpoint.json')
    LARGE_SCAN_DIR = os.path.join(DATA_DIR, 'large_scans')
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)
    os.makedirs(LARGE_SCAN_DIR, exist_ok=True)
    print(f"✅ Using fallback directory: {DATA_DIR}")

PORT = int(os.environ.get('PORT', 5000))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(SCRIPT_DIR, 'frontend')
os.makedirs(FRONTEND_DIR, exist_ok=True)

FRONTEND_PORT = int(os.environ.get('FRONTEND_PORT', 8000))
BACKEND_URL = os.environ.get('BACKEND_URL', f'http://localhost:{PORT}')

# XRP RPC Configuration
XRP_RPC_URL = "https://s1.ripple.com:51234/"
ALTERNATE_RPC_URLS = [
    "https://s2.ripple.com:51234/",
    "https://xrplcluster.com/",
    "https://xrpl.ws/"
]

# Performance Settings
MAX_SCAN_LIMIT = 1000000
WEBHOOK_TIMEOUT = 10
COMPRESSION_THRESHOLD = 1024 * 500
REQUEST_DELAY = 0.005
MAX_RETRIES = 3
BATCH_SIZE = 1000
MAX_WORKERS = 50
pool_connections = 200
pool_maxsize = 200
pool_block = False

active_scans = {}
scan_lock = threading.Lock()
thread_local = threading.local()

# ==================== HELPER FUNCTIONS ====================
def create_optimized_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy,
        pool_block=pool_block
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        'Connection': 'keep-alive',
        'Keep-Alive': 'timeout=60, max=1000'
    })
    return session

def get_thread_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = create_optimized_session()
    return thread_local.session

def make_xrp_request(payload, retry_count=0):
    urls = [XRP_RPC_URL] + ALTERNATE_RPC_URLS
    session = get_thread_session()
    for url in urls:
        try:
            headers = {'Content-Type': 'application/json', 'Connection': 'keep-alive'}
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
    payload = {
        "method": "account_info",
        "params": [{"account": wallet_address, "ledger_index": "validated"}]
    }
    try:
        result = make_xrp_request(payload)
        return result.get('result', {}).get('account_data', {})
    except:
        return None

def get_transaction_count(wallet_address):
    try:
        account_info = get_account_info(wallet_address)
        if account_info:
            return account_info.get('PreviousTxnCount', 0)
    except:
        pass
    return None

def scan_transactions_batch(wallet_address, marker=None, limit=BATCH_SIZE):
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
    except:
        return None

def is_valid_missing_tag_transaction(tx_data, tx_meta, wallet_address):
    if tx_data.get('TransactionType') != 'Payment':
        return False
    if tx_meta.get('TransactionResult', '') != 'tesSUCCESS':
        return False
    if tx_data.get('Destination') != wallet_address:
        return False
    if tx_data.get('DestinationTag') is not None:
        return False
    memos = tx_data.get('Memos')
    if memos is not None and len(memos) > 0:
        for memo in memos:
            if memo.get('Memo', {}).get('MemoData'):
                return False
        if len(memos) > 0:
            return False
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
    if amount_drops <= 0:
        return False
    if not tx_data.get('hash') or not tx_data.get('Account'):
        return False
    return True

def process_transactions_batch(transactions, wallet_address):
    missing_tags = []
    for tx in transactions:
        try:
            tx_data = tx.get('tx', {})
            tx_meta = tx.get('meta', {})
            if tx_data.get('TransactionType') != 'Payment':
                continue
            if tx_data.get('Destination') != wallet_address:
                continue
            if not is_valid_missing_tag_transaction(tx_data, tx_meta, wallet_address):
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
            missing_tags.append({
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
    filename = f"{LARGE_SCAN_DIR}/{hashlib.md5(wallet_address.encode()).hexdigest()}_checkpoint.json"
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return None

def compress_response(data):
    response = make_response(json.dumps(data))
    if len(response.data) > COMPRESSION_THRESHOLD:
        response.data = gzip.compress(response.data)
        response.headers['Content-Encoding'] = 'gzip'
    return response

def validate_wallet_address(address):
    if not address or not isinstance(address, str):
        return False
    return address.startswith('r') and 25 <= len(address) <= 35

def send_webhook_notification(webhook_url, payload):
    try:
        requests.post(webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
    except:
        pass

def log_request_info(response):
    print(f"[{datetime.now().isoformat()}] {request.method} {request.path} - Status: {response.status_code}")
    return response

def get_frontend_url():
    if os.environ.get('RENDER'):
        render_url = os.environ.get('RENDER_EXTERNAL_URL', '')
        if render_url:
            return render_url
        return f"https://{os.environ.get('RENDER_SERVICE_NAME', 'xrp-scanner')}.onrender.com"
    if os.environ.get('FRONTEND_URL'):
        return os.environ.get('FRONTEND_URL')
    return f"http://localhost:{FRONTEND_PORT}"

def get_backend_url():
    if os.environ.get('RENDER'):
        render_url = os.environ.get('RENDER_EXTERNAL_URL', '')
        if render_url:
            return render_url
        return f"https://{os.environ.get('RENDER_SERVICE_NAME', 'xrp-scanner')}.onrender.com"
    if os.environ.get('BACKEND_URL'):
        return os.environ.get('BACKEND_URL')
    return f"http://localhost:{PORT}"

def build_live_file_links(wallet_address):
    base_url = get_frontend_url()
    backend_url = get_backend_url()
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
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "download_url": f"{backend_url}/api/files/{filename}",
                "view_url": f"{backend_url}/api/files/view/{filename}",
                "explorer_url": f"{base_url}/explorer?file={filename}",
                "iframe_url": f"{backend_url}/api/files/view/{filename}"
            })
    return sorted(files, key=lambda x: x["created_at"], reverse=True)

def get_generated_files(scan_id, wallet_address=None):
    files = []
    backend_url = get_backend_url()
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
            files.append({
                'type': file_type,
                'filename': filename,
                'download_url': f'/api/files/{filename}',
                'view_url': f'/api/files/view/{filename}',
                'full_download_url': f"{backend_url}/api/files/{filename}",
                'full_view_url': f"{backend_url}/api/files/view/{filename}",
                'size': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
    return sorted(files, key=lambda x: x['created_at'], reverse=True)

def save_scan_files_metadata(scan_id, wallet_address):
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
    preview = {'headers': [], 'rows': [], 'total_rows': 0, 'preview_rows': max_rows}
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
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    return json.dumps({'data': data}, indent=2, default=str)

def generate_html_table(preview_data):
    html = """<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #0a0a0a; color: #00ff00; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #1a1a1a; }
        .warning { background-color: #ff9800; color: white; padding: 10px; margin-bottom: 20px; }
        .error { background-color: #f44336; color: white; padding: 10px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>CSV File Preview</h1>"""
    if 'warning' in preview_data:
        html += f'<div class="warning">{preview_data["warning"]}</div>'
    if 'error' in preview_data:
        html += f'<div class="error">{preview_data["error"]}</div></body></html>'
        return html
    html += f'<p>Total rows: {preview_data["total_rows"]}</p><table><thead><tr>'
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
    filename = f"{LARGE_SCAN_DIR}/{wallet_address}_batch_{batch_number}.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, 'a', newline='') as f:
        if transactions:
            writer = csv.DictWriter(f, fieldnames=transactions[0].keys())
            if not file_exists:
                writer.writeheader()
            writer.writerows(transactions)

def append_to_log(log_entry):
    try:
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)
    except:
        logs = []
    logs.append(log_entry)
    if len(logs) > 1000:
        logs = logs[-1000:]
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def large_scan_worker(wallet_address, scan_id, max_transactions=None, callback=None):
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
                'scan_mode': 'EXTREME_DEPTH',
                'frontend_url': get_frontend_url(),
                'backend_url': get_backend_url()
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
                            'last_batch': {'count': batch_count, 'missing': len(batch_missing), 'amount': batch_amount},
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
                            'last_batch': {'count': batch_count, 'missing': 0, 'amount': 0},
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
                callback({'scan_id': scan_id, 'processed': processed_count, 'missing': missing_count, 'total_amount': total_amount, 'batch': batch_missing})
        
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
                },
                'frontend_url': get_frontend_url(),
                'backend_url': get_backend_url()
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
        
        append_to_log({
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
        })
        return {'success': True, 'scan_id': scan_id, 'processed': processed_count, 'missing': missing_count, 'total_amount': total_amount, 'file': final_filename, 'files': generated_files}
    except Exception as e:
        print(f"Scan worker error: {e}")
        import traceback
        traceback.print_exc()
        with scan_lock:
            if scan_id in active_scans:
                active_scans[scan_id]['status'] = 'error'
                active_scans[scan_id]['error'] = str(e)
        return {'success': False, 'scan_id': scan_id, 'error': str(e)}

# ==================== FRONTEND HTML GENERATION ====================
def create_frontend_index_html():
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    if not os.path.exists(index_path):
        backend_url = get_backend_url()
        frontend_url = get_frontend_url()
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XRP Sentinel - Enterprise Tag Monitor | Blockchain Verified</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%23000'/%3E%3Ccircle cx='50' cy='50' r='45' fill='none' stroke='%2300E5BF' stroke-width='4'/%3E%3Cpath d='M50 20 L65 35 L50 50 L35 35 Z' fill='%230066FF' stroke='%2300E5BF' stroke-width='2'/%3E%3Cpath d='M50 50 L65 65 L50 80 L35 65 Z' fill='%2300E5BF' stroke='%230066FF' stroke-width='2'/%3E%3Ccircle cx='50' cy='35' r='3' fill='%23FFF'/%3E%3Ccircle cx='50' cy='65' r='3' fill='%23FFF'/%3E%3C/svg%3E">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary-500: #0066ff;
            --accent-500: #00e5bf;
            --neutral-900: #0f172a;
            --neutral-800: #1e293b;
            --neutral-700: #334155;
            --neutral-400: #94a3b8;
            --neutral-100: #f1f5f9;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
            --gradient-primary: linear-gradient(135deg, #0066ff, #00e5bf);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; background: #020617; color: var(--neutral-100); line-height: 1.5; }}
        .app {{ display: flex; min-height: 100vh; }}
        .sidebar {{ width: 280px; background: var(--neutral-900); border-right: 1px solid var(--neutral-800); position: fixed; top: 0; left: 0; bottom: 0; }}
        .logo-container {{ padding: 24px; border-bottom: 1px solid var(--neutral-800); }}
        .logo {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
        .logo-text {{ font-size: 1.5rem; font-weight: 700; background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .logo-text span {{ font-weight: 300; }}
        .badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; background: var(--primary-500); color: white; font-size: 0.7rem; font-weight: 600; border-radius: 4px; }}
        .nav-menu {{ padding: 24px 16px; }}
        .nav-item {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; color: var(--neutral-400); text-decoration: none; border-radius: 8px; margin-bottom: 4px; }}
        .nav-item:hover {{ background: var(--neutral-800); color: var(--neutral-100); }}
        .nav-item.active {{ background: var(--gradient-primary); color: white; }}
        .nav-footer {{ padding: 24px; border-top: 1px solid var(--neutral-800); }}
        .system-status {{ display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--neutral-400); margin-bottom: 8px; }}
        .status-indicator {{ width: 8px; height: 8px; border-radius: 50%; }}
        .status-indicator.online {{ background: var(--success); box-shadow: 0 0 0 2px rgba(16,185,129,0.2); animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .version {{ font-size: 0.75rem; color: var(--neutral-600); }}
        .main-content {{ flex: 1; margin-left: 280px; padding: 24px; }}
        .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }}
        .page-title {{ display: flex; align-items: center; gap: 16px; }}
        .page-title h1 {{ font-size: 2rem; font-weight: 700; background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .live-badge {{ display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: rgba(16,185,129,0.1); border-radius: 20px; font-size: 0.75rem; color: var(--success); }}
        .pulse {{ width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 2s infinite; }}
        .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; border: none; }}
        .btn-primary {{ background: var(--gradient-primary); color: white; }}
        .btn-primary:hover {{ transform: translateY(-1px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }}
        .btn-secondary {{ background: var(--neutral-800); color: var(--neutral-100); border: 1px solid var(--neutral-700); }}
        .btn-icon {{ padding: 8px; background: var(--neutral-800); color: var(--neutral-400); border: 1px solid var(--neutral-700); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 32px; }}
        .stat-card {{ background: var(--neutral-900); border: 1px solid var(--neutral-800); border-radius: 16px; padding: 20px; display: flex; align-items: center; gap: 16px; }}
        .stat-card:hover {{ transform: translateY(-2px); border-color: var(--primary-500); }}
        .stat-icon {{ width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }}
        .stat-icon.blue {{ background: rgba(0,102,255,0.1); color: var(--primary-500); }}
        .stat-icon.green {{ background: rgba(16,185,129,0.1); color: var(--success); }}
        .stat-icon.orange {{ background: rgba(245,158,11,0.1); color: var(--warning); }}
        .stat-icon.purple {{ background: rgba(139,92,246,0.1); color: #8b5cf6; }}
        .stat-details {{ flex: 1; }}
        .stat-label {{ font-size: 0.8rem; color: var(--neutral-500); }}
        .stat-value {{ font-size: 1.5rem; font-weight: 700; }}
        .panel {{ background: var(--neutral-900); border: 1px solid var(--neutral-800); border-radius: 20px; margin-bottom: 24px; overflow: hidden; }}
        .panel-header {{ padding: 20px 24px; border-bottom: 1px solid var(--neutral-800); display: flex; justify-content: space-between; align-items: center; }}
        .panel-header h2 {{ font-size: 1.2rem; font-weight: 600; }}
        .panel-body {{ padding: 24px; }}
        .input-field label {{ display: block; font-size: 0.9rem; color: var(--neutral-400); margin-bottom: 8px; }}
        .input-field input {{ width: 100%; padding: 14px 16px; background: var(--neutral-800); border: 1px solid var(--neutral-700); border-radius: 10px; color: var(--neutral-100); font-family: monospace; }}
        .input-field input:focus {{ outline: none; border-color: var(--primary-500); }}
        .scan-options {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
        .option-item select {{ width: 100%; padding: 12px; background: var(--neutral-800); border: 1px solid var(--neutral-700); border-radius: 8px; color: var(--neutral-100); }}
        .action-buttons {{ display: flex; gap: 12px; margin-top: 24px; }}
        .loading-overlay {{ position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(2,6,23,0.9); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; }}
        .loading-spinner {{ width: 60px; height: 60px; border: 3px solid var(--neutral-700); border-top-color: var(--primary-500); border-right-color: var(--accent-500); border-radius: 50%; animation: spin 1s infinite; margin: 0 auto 20px; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .table-container {{ overflow-x: auto; border-radius: 12px; background: var(--neutral-800); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 16px; font-size: 0.85rem; color: var(--neutral-400); border-bottom: 1px solid var(--neutral-700); }}
        td {{ padding: 16px; border-bottom: 1px solid var(--neutral-700); color: var(--neutral-300); }}
        tr:hover td {{ background: var(--neutral-750); }}
        .tag-missing {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; background: rgba(239,68,68,0.1); color: var(--danger); border-radius: 6px; font-size: 0.8rem; font-weight: 600; }}
        .empty-state {{ text-align: center; padding: 48px; color: var(--neutral-600); }}
        .toast {{ position: fixed; top: 24px; right: 24px; padding: 12px 20px; background: var(--neutral-900); border-radius: 8px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.25); z-index: 1100; animation: slideInRight 0.3s ease; }}
        @keyframes slideInRight {{ from {{ transform: translateX(100%); opacity: 0; }} to {{ transform: translateX(0); opacity: 1; }} }}
        .toast-success {{ border-left: 4px solid var(--success); }}
        .toast-error {{ border-left: 4px solid var(--danger); }}
        @media (max-width: 768px) {{ .sidebar {{ display: none; }} .main-content {{ margin-left: 0; }} .stats-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="app">
        <nav class="sidebar">
            <div class="logo-container"><div class="logo"><svg width="32" height="32" viewBox="0 0 32 32" fill="none"><path d="M16 2L4 8v12l12 6 12-6V8l-12-6z" stroke="url(#gradient)" stroke-width="2" fill="none"/><path d="M16 14l6-3v6l-6 3-6-3v-6l6 3z" fill="url(#gradient)"/><defs><linearGradient id="gradient" x1="4" y1="8" x2="28" y2="24"><stop stop-color="#0066FF"/><stop offset="1" stop-color="#00E5BF"/></linearGradient></defs></svg><span class="logo-text">XRP<span>Sentinel</span></span></div><div class="badge">Enterprise</div></div>
            <div class="nav-menu"><a href="#" class="nav-item active">Dashboard</a><a href="#" class="nav-item">Scans</a><a href="#" class="nav-item">Analytics</a><a href="#" class="nav-item">Profile</a></div>
            <div class="nav-footer"><div class="system-status"><div class="status-indicator online"></div><span>XRP Ledger: Connected</span></div><div class="version">v2.0.0 · Enterprise</div></div>
        </nav>
        <main class="main-content">
            <header class="top-bar"><div class="page-title"><h1>Transaction Monitor</h1><span class="live-badge"><span class="pulse"></span>Live</span></div><div class="header-actions"><button class="btn btn-secondary" onclick="refreshLogs()">Refresh</button><div class="user-menu"><span class="user-avatar">JD</span></div></div></header>
            <div class="content">
                <div class="stats-grid" id="analyticsStats">
                    <div class="stat-card"><div class="stat-icon blue"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div><div class="stat-details"><span class="stat-label">Total Scans</span><span class="stat-value" id="totalScans">-</span></div></div>
                    <div class="stat-card"><div class="stat-icon green"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg></div><div class="stat-details"><span class="stat-label">Total XRP at Risk</span><span class="stat-value" id="totalXRP">-</span></div></div>
                    <div class="stat-card"><div class="stat-icon orange"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div><div class="stat-details"><span class="stat-label">Missing Tags</span><span class="stat-value" id="totalMissing">-</span></div></div>
                    <div class="stat-card"><div class="stat-icon purple"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 12H4M12 4v16"/></svg></div><div class="stat-details"><span class="stat-label">Avg/Scan</span><span class="stat-value" id="avgMissing">-</span></div></div>
                </div>
                <div class="panel scan-panel"><div class="panel-header"><h2>New Scan</h2><span class="badge" style="background:#10b981;">🔗 Blockchain Verified</span></div><div class="panel-body"><div class="scan-form"><div class="input-group"><div class="input-field"><label>Wallet Address</label><input type="text" id="walletAddress" placeholder="rXXXXXXXXXXXXXXXXXXXXXXXXX" value="rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"></div><div class="scan-options"><div class="option-item"><label>Scan Depth</label><select id="limit"><option value="100">Standard (100 txs)</option><option value="500">Deep (500 txs)</option><option value="1000">Extended (1000 txs)</option></select></div><div class="option-item"><label>Mode</label><select id="scanMode"><option value="standard">Standard Scan (Blockchain Verified)</option><option value="large">Large Scan (All - Blockchain Verified)</option></select></div></div></div><div class="action-buttons"><button onclick="scanWallet()" id="scanBtn" class="btn btn-primary">Start Verified Scan</button><button onclick="startLargeScan()" id="largeScanBtn" class="btn btn-secondary">Large Scan (All)</button></div></div><div id="scanProgress" class="scan-progress" style="display:none;"><div class="progress-header"><span class="progress-title">Large Scan in Progress</span><span class="progress-percentage">0%</span></div><div class="progress-track"><div class="progress-bar"></div></div><div class="progress-stats"></div><div class="progress-status"></div></div></div></div>
                <div id="loading" class="loading-overlay" style="display:none;"><div class="loading-content"><div class="loading-spinner"></div><p>Scanning wallet on XRP Ledger</p><span class="loading-sub">This may take a moment</span></div></div>
                <div class="panel results-panel" id="summarySection" style="display:none;"><div class="panel-header"><div class="panel-title"><h2>Scan Results</h2><span class="result-badge" id="resultCount">0 found</span><span class="result-badge" style="background:#10b981;">🔗 Blockchain Verified</span></div><div class="panel-actions"><button onclick="downloadData('csv')" class="btn btn-icon" title="Download CSV">📥</button><button onclick="downloadData('json')" class="btn btn-icon" title="Download JSON">📄</button></div></div><div class="panel-body"><div class="summary-stats" id="statsGrid"></div><div class="table-container"><table><thead><tr><th>Date & Time</th><th>Transaction Hash</th><th>Sender</th><th>Amount (XRP)</th><th>Destination Tag</th><th>Validation</th><th>Actions</th></tr></thead><tbody id="tableBody"><tr><td colspan="7" class="empty-state">No data yet. Start a scan to see results.</td></tr></tbody></table></div></div></div>
                <div class="panel logs-panel"><div class="panel-header"><h2>Activity Log</h2><button onclick="refreshLogs()" class="btn btn-icon">🔄</button></div><div class="panel-body"><div class="logs-container" id="logsContainer"><div class="empty-state">No scan history available</div></div></div></div>
            </div>
        </main>
    </div>
    <div id="connectionStatus" style="position:fixed;bottom:20px;right:20px;padding:8px 16px;border-radius:8px;font-size:12px;background:#1e293b;border:1px solid #334155;cursor:pointer;z-index:1000;" onclick="showBackendConfig()">🔌 Checking API...</div>
    <script>
        let API_BASE = '{backend_url}';
        let activeScanId = null, scanPollInterval = null, liveFilesInterval = null, currentFiles = [], currentScanId = null;
        
        async function discoverBackendUrl() {{
            const possibleUrls = [window.location.origin, '{backend_url}', 'http://localhost:5000'];
            for (const url of possibleUrls) {{
                try {{
                    const testUrl = `${{url.replace(/\\/$/, '')}}/api/test`;
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 2000);
                    const response = await fetch(testUrl, {{ signal: controller.signal }});
                    clearTimeout(timeoutId);
                    if (response.ok) {{
                        const data = await response.json();
                        if (data.status === 'ok') {{
                            localStorage.setItem('xrp_backend_url', url);
                            return url;
                        }}
                    }}
                }} catch(e) {{}}
            }}
            return '/api';
        }}
        
        async function initializeBackend() {{
            const discovered = await discoverBackendUrl();
            API_BASE = discovered.replace(/\\/$/, '') + '/api';
            console.log('API_BASE:', API_BASE);
            try {{
                const resp = await fetch(`${{API_BASE}}/test`);
                if (resp.ok) {{
                    document.getElementById('connectionStatus').innerHTML = '✅ API Online<br>Click to change';
                    return true;
                }}
            }} catch(e) {{}}
            document.getElementById('connectionStatus').innerHTML = '❌ API Offline<br>Click to configure';
            return false;
        }}
        
        function showBackendConfig() {{
            const url = prompt('Enter backend URL (e.g., http://localhost:5000):', localStorage.getItem('xrp_backend_url') || 'http://localhost:5000');
            if (url) {{
                localStorage.setItem('xrp_backend_url', url);
                location.reload();
            }}
        }}
        
        function showNotification(msg, type) {{
            const toast = document.createElement('div');
            toast.className = `toast toast-${{type}}`;
            toast.innerHTML = `<div class="toast-content"><span>${{msg}}</span></div>`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }}
        
        function formatHash(hash) {{ return hash ? hash.substring(0,6)+'...'+hash.substring(hash.length-6) : 'N/A'; }}
        
        async function loadAnalytics() {{
            try {{
                const resp = await fetch(`${{API_BASE}}/analytics/summary`);
                const data = await resp.json();
                document.getElementById('totalScans').innerText = data.total_scans || '0';
                document.getElementById('totalXRP').innerText = (data.total_xrp_at_risk || 0).toFixed(2) + ' XRP';
                document.getElementById('totalMissing').innerText = (data.total_missing_tags || 0).toLocaleString();
                document.getElementById('avgMissing').innerText = (data.average_missing_per_scan || 0).toFixed(2);
            }} catch(e) {{ console.error(e); }}
        }}
        
        async function refreshLogs() {{
            try {{
                const resp = await fetch(`${{API_BASE}}/logs`);
                const data = await resp.json();
                const container = document.getElementById('logsContainer');
                if (data.logs && data.logs.length) {{
                    container.innerHTML = data.logs.reverse().map(log => `<div class="log-entry"><span class="log-timestamp">${{new Date(log.timestamp).toLocaleString()}}</span> <span>🔗 Scanned <strong>${{formatHash(log.wallet || log.address || '')}}</strong>: found <strong>${{log.transactions_found || log.missing_tags_found || 0}}</strong> missing tags</span></div>`).join('');
                }} else {{
                    container.innerHTML = '<div class="empty-state">No scan history available</div>';
                }}
            }} catch(e) {{ console.error(e); }}
        }}
        
        async function scanWallet() {{
            const address = document.getElementById('walletAddress').value.trim();
            const limit = document.getElementById('limit').value;
            const mode = document.getElementById('scanMode').value;
            if (!address || !address.startsWith('r') || address.length < 25) {{ showNotification('Invalid XRP address', 'error'); return; }}
            if (mode === 'large') {{ startLargeScan(); return; }}
            document.getElementById('loading').style.display = 'flex';
            document.getElementById('scanBtn').disabled = true;
            try {{
                const resp = await fetch(`${{API_BASE}}/scan`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ address, limit: parseInt(limit) }})
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    displayResults(data);
                    refreshLogs();
                    loadAnalytics();
                    showNotification(`Found ${{data.transactions.length}} transactions missing tags`, 'success');
                }} else {{ showNotification(data.error || 'Scan failed', 'error'); }}
            }} catch(e) {{ showNotification('Network error: ' + e.message, 'error'); }}
            finally {{ document.getElementById('loading').style.display = 'none'; document.getElementById('scanBtn').disabled = false; }}
        }}
        
        async function startLargeScan() {{
            const address = document.getElementById('walletAddress').value.trim();
            if (!address) {{ showNotification('Enter wallet address', 'warning'); return; }}
            if (!confirm('🔍 This will scan ALL transactions for ' + address + ' with full XRPL validation. Continue?')) return;
            showNotification('Starting large scan...', 'info');
            try {{
                const resp = await fetch(`${{API_BASE}}/scan/large`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ address }})
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    currentScanId = data.scan_id;
                    activeScanId = data.scan_id;
                    showNotification(`Large scan started! ID: ${{data.scan_id}}`, 'success');
                    document.getElementById('scanProgress').style.display = 'block';
                    if (scanPollInterval) clearInterval(scanPollInterval);
                    scanPollInterval = setInterval(async () => {{
                        try {{
                            const statusResp = await fetch(`${{API_BASE}}/scan/status/${{data.scan_id}}`);
                            const status = await statusResp.json();
                            if (statusResp.ok) {{
                                const percent = status.progress || 0;
                                document.querySelector('#scanProgress .progress-percentage').innerText = percent.toFixed(1) + '%';
                                document.querySelector('#scanProgress .progress-bar').style.width = percent + '%';
                                document.querySelector('#scanProgress .progress-stats').innerHTML = `<span>📊 Processed: ${{(status.processed || 0).toLocaleString()}}</span><span>⚠️ Missing: ${{status.missing || 0}}</span><span>💰 Total: ${{(status.total_amount || 0).toFixed(2)}} XRP</span>`;
                                document.querySelector('#scanProgress .progress-status').innerHTML = `Status: ${{status.status}} | Blockchain Validation Active`;
                                if (status.status === 'completed') {{
                                    clearInterval(scanPollInterval);
                                    scanPollInterval = null;
                                    document.getElementById('scanProgress').style.display = 'none';
                                    showNotification(`✅ Scan completed! Found ${{status.missing}} missing tags`, 'success');
                                    refreshLogs();
                                    loadAnalytics();
                                    if (status.downloads && status.downloads.length) showFileDownloadPanel(status.downloads);
                                }} else if (status.status === 'error') {{
                                    clearInterval(scanPollInterval);
                                    document.getElementById('scanProgress').style.display = 'none';
                                    showNotification(`Scan error: ${{status.error}}`, 'error');
                                }}
                            }}
                        }} catch(e) {{ console.error(e); }}
                    }}, 2000);
                }} else {{ showNotification(data.error || 'Failed to start scan', 'error'); }}
            }} catch(e) {{ showNotification('Network error: ' + e.message, 'error'); }}
        }}
        
        function showFileDownloadPanel(files) {{
            currentFiles = files;
            let panel = document.getElementById('fileDownloadPanel');
            if (!panel) {{
                panel = document.createElement('div');
                panel.id = 'fileDownloadPanel';
                panel.className = 'panel';
                panel.style.marginTop = '20px';
                document.querySelector('.content').appendChild(panel);
            }}
            panel.innerHTML = `<div class="panel-header"><h3>📁 Generated Files (${{files.length}})</h3><button onclick="this.parentElement.parentElement.remove()" style="background:none;border:none;color:#fff;font-size:20px;">×</button></div><div class="panel-body">${{files.map(f => `<div style="display:flex;justify-content:space-between;align-items:center;padding:12px;border-bottom:1px solid #334155;"><div><strong>${{f.filename}}</strong><br><small>${{(f.size/1024).toFixed(1)}} KB</small></div><div><button onclick="downloadFile('${{f.filename}}')" class="btn btn-icon">💾</button> <button onclick="viewFile('${{f.filename}}')" class="btn btn-icon">👁️</button></div></div>`).join('')}}</div>`;
            panel.style.display = 'block';
        }}
        
        async function downloadFile(filename) {{
            window.open(`${{API_BASE}}/files/${{filename}}`, '_blank');
        }}
        
        function viewFile(filename) {{
            window.open(`${{API_BASE}}/files/view/${{filename}}`, '_blank');
        }}
        
        async function downloadData(format) {{
            window.open(`${{API_BASE}}/download/${{format}}`, '_blank');
        }}
        
        function displayResults(data) {{
            const transactions = data.transactions || [];
            const summary = data.summary || {};
            document.getElementById('summarySection').style.display = 'block';
            document.getElementById('resultCount').innerText = `${{transactions.length}} found`;
            document.getElementById('statsGrid').innerHTML = `<div class="stat-card"><div class="stat-details"><span class="stat-label">Scanned</span><span class="stat-value">${{summary.total_transactions_scanned || 0}}</span></div></div><div class="stat-card"><div class="stat-details"><span class="stat-label">Missing (Verified)</span><span class="stat-value">${{summary.missing_tag_count || 0}}</span></div></div><div class="stat-card"><div class="stat-details"><span class="stat-label">Total XRP</span><span class="stat-value">${{(summary.total_amount_missing_tags || 0).toFixed(2)}}</span></div></div>`;
            const tbody = document.getElementById('tableBody');
            if (!transactions.length) {{
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">✅ No transactions found missing destination tags</td></tr>';
                return;
            }}
            tbody.innerHTML = transactions.map(tx => `<tr><td>${{new Date(tx.date).toLocaleString()}}</td><td><a href="https://xrpscan.com/tx/${{tx.hash}}" target="_blank">${{formatHash(tx.hash)}}</a></td><td>${{formatHash(tx.sender)}}</td><td class="amount">${{tx.amount.toFixed(6)}} XRP</td><td><span class="tag-missing">⚠️ MISSING</span></td><td><span style="color:#10b981;">✓ Verified</span></td><td><a href="https://xrpscan.com/tx/${{tx.hash}}" target="_blank">View</a></td></tr>`).join('');
        }}
        
        document.addEventListener('DOMContentLoaded', async () => {{
            await initializeBackend();
            await refreshLogs();
            await loadAnalytics();
            document.getElementById('walletAddress').addEventListener('keypress', e => {{ if(e.key === 'Enter') scanWallet(); }});
        }});
        window.scanWallet = scanWallet; window.startLargeScan = startLargeScan; window.downloadData = downloadData; window.refreshLogs = refreshLogs; window.downloadFile = downloadFile; window.viewFile = viewFile; window.showBackendConfig = showBackendConfig;
    </script>
</body>
</html>'''
        with open(index_path, 'w') as f:
            f.write(html_content)
        print(f"✅ Created frontend index.html at {index_path}")
    return index_path

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    return jsonify({
        "name": "XRP Extreme Depth Wallet Scanner",
        "version": "2.0.0",
        "status": "online",
        "description": "Blockchain-verified XRP transaction scanner for missing DestinationTags and Memos",
        "endpoints": {k: f"/api/{k}" for k in ["scan", "scan/large", "scan/status/<id>", "files/<filename>", "files/view/<filename>", "test", "logs", "analytics/summary", "download/<format>"]},
        "data_directory": DATA_DIR,
        "frontend_url": get_frontend_url(),
        "backend_url": get_backend_url()
    })

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({"status": "ok", "message": "API working with EXTREME DEPTH scanning!", "validation": "Blockchain-level verification", "features": ["Extreme depth scanning", "FULL blockchain scan", "File endpoints", "Live streaming"]})

@app.route('/api/scan', methods=['POST'])
def scan_wallet():
    try:
        data = request.json
        if not data: return jsonify({"error": "No JSON data"}), 400
        wallet_address = data.get('address')
        limit = min(int(data.get('limit', 1000)), 10000000000)
        if not wallet_address or not validate_wallet_address(wallet_address): return jsonify({"error": "Invalid wallet address"}), 400
        result = scan_transactions_batch(wallet_address, limit=limit)
        if not result: return jsonify({"error": "Failed to scan wallet"}), 500
        transactions = result.get('transactions', [])
        missing_tag_txs = process_transactions_batch(transactions, wallet_address)
        amounts = [tx['amount'] for tx in missing_tag_txs]
        dates = [tx['date'] for tx in missing_tag_txs if tx['date'] != 'Unknown']
        summary = {"total_transactions_scanned": len(transactions), "missing_tag_count": len(missing_tag_txs), "total_amount_missing_tags": sum(amounts), "oldest_transaction": min(dates) if dates else None, "newest_transaction": max(dates) if dates else None, "validation_method": "blockchain_level_verification"}
        append_to_log({"timestamp": datetime.now().isoformat(), "wallet": wallet_address, "transactions_found": len(missing_tag_txs), "type": "standard", "validation_type": "blockchain_verified"})
        return jsonify({"transactions": missing_tag_txs, "summary": summary, "pagination": {"limit": limit, "marker": result.get('marker'), "has_more": result.get('marker') is not None}, "validation_info": {"method": "XRPL blockchain verification", "checks_performed": ["Transaction type = Payment", "Transaction result = tesSUCCESS", "No DestinationTag", "No Memos", "Valid delivered amount"]}})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/scan/large', methods=['POST'])
def start_large_scan():
    try:
        data = request.json
        if not data: return jsonify({"error": "No JSON data"}), 400
        wallet_address = data.get('address')
        max_transactions = data.get('max_transactions', None)
        if not wallet_address or not validate_wallet_address(wallet_address): return jsonify({"error": "Invalid wallet address"}), 400
        scan_id = hashlib.md5(f"{wallet_address}_{time.time()}".encode()).hexdigest()[:12]
        total_tx = get_account_info(wallet_address).get('PreviousTxnCount', 'unknown') if get_account_info(wallet_address) else 'unknown'
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(large_scan_worker, wallet_address, scan_id, max_transactions, None)
        with scan_lock:
            active_scans[scan_id] = {'status': 'starting', 'wallet': wallet_address, 'processed': 0, 'missing': 0, 'total_amount': 0, 'total_estimate': total_tx, 'progress': 0, 'validation': 'blockchain_verified'}
        return jsonify({'scan_id': scan_id, 'status': 'started', 'message': f'Large scan initiated for {wallet_address}', 'estimated_transactions': total_tx, 'checkpoint': f'/api/scan/status/{scan_id}', 'validation_type': 'blockchain_level_verification'})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/scan/status/<scan_id>', methods=['GET'])
def get_scan_status(scan_id):
    with scan_lock:
        if scan_id in active_scans:
            scan_data = active_scans[scan_id].copy()
            if scan_data.get('wallet'): scan_data['live_files'] = build_live_file_links(scan_data['wallet'])
            if scan_data.get('status') == 'completed' and not scan_data.get('downloads') and scan_data.get('wallet'):
                scan_data['downloads'] = get_generated_files(scan_id, scan_data['wallet'])
            return jsonify({"success": True, **scan_data})
        return jsonify({"success": False, "error": "Scan not found"}), 404

@app.route('/api/files/<filename>', methods=['GET'])
def download_file(filename):
    if not is_safe_file(filename): return jsonify({"error": "Invalid file name"}), 400
    filepath = os.path.abspath(os.path.join(LARGE_SCAN_DIR, filename))
    if not os.path.exists(filepath): return jsonify({"error": "File not found"}), 404
    if not filepath.startswith(os.path.abspath(LARGE_SCAN_DIR)): return jsonify({"error": "Access denied"}), 403
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/files/view/<filename>', methods=['GET'])
def view_file(filename):
    if not is_safe_file(filename): return jsonify({"error": "Invalid file name"}), 400
    filepath = os.path.abspath(os.path.join(LARGE_SCAN_DIR, filename))
    if not os.path.exists(filepath): return jsonify({"error": "File not found"}), 404
    if filename.endswith('.json'):
        preview = preview_json_file(filepath)
        if 'error' in preview: return jsonify(preview), 500
        return app.response_class(format_json_for_browser(preview.get('data', {})), mimetype='application/json')
    elif filename.endswith('.csv'):
        preview = preview_csv_file(filepath)
        if 'error' in preview: return jsonify(preview), 500
        return generate_html_table(preview), 200, {'Content-Type': 'text/html'}
    return jsonify({"error": "Preview not available for this file type"}), 400

@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f: logs = json.load(f)
            return jsonify({"logs": logs[-50:]})
        return jsonify({"logs": []})
    except: return jsonify({"logs": []})

@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    total_scans = total_transactions = total_missing = total_amount = 0
    try:
        with open(LOG_FILE, 'r') as f: logs = json.load(f)
        for log in logs:
            if log.get('type') == 'standard' or log.get('status') == 'completed':
                total_scans += 1
                total_transactions += log.get('transactions_scanned', 0)
                total_missing += log.get('missing_tags_found', 0)
                total_amount += log.get('total_amount_xrp', 0)
    except: pass
    return jsonify({'total_scans': total_scans, 'total_transactions_scanned': total_transactions, 'total_missing_tags': total_missing, 'total_xrp_at_risk': total_amount, 'average_missing_per_scan': total_missing / total_scans if total_scans > 0 else 0, 'validation_method': 'blockchain_level_verification'})

@app.route('/api/download/<format>', methods=['GET'])
def download_data(format):
    try:
        if format == 'csv':
            latest_csv = max([f for f in glob.glob(os.path.join(LARGE_SCAN_DIR, '*.csv'))], key=os.path.getmtime, default=None)
            if latest_csv: return send_file(latest_csv, as_attachment=True, download_name='xrp_missing_tags.csv')
        elif format == 'json':
            if os.path.exists(LOG_FILE): return send_file(LOG_FILE, as_attachment=True, download_name='scan_history.json')
        return jsonify({"error": "File not found"}), 404
    except: return jsonify({"error": "No data available"}), 404

@app.route('/frontend/<path:filename>')
def serve_frontend_file(filename):
    safe_path = os.path.normpath(filename).lstrip('/')
    if '..' in safe_path or safe_path.startswith('..'): return jsonify({"error": "Invalid path"}), 403
    file_path = os.path.join(FRONTEND_DIR, safe_path)
    if os.path.exists(file_path) and os.path.isfile(file_path): return send_file(file_path)
    return jsonify({"error": "File not found"}), 404

@app.route('/frontend/')
@app.route('/frontend/index.html')
def serve_frontend_index():
    create_frontend_index_html()
    return send_file(os.path.join(FRONTEND_DIR, 'index.html'))

@app.after_request
def after_request_logging(response):
    print(f"[{datetime.now().isoformat()}] {request.method} {request.path} - {response.status_code}")
    return response

if __name__ == '__main__':
    print("="*60)
    print("XRP EXTREME DEPTH Wallet Scanner (100M+ Transaction Support)")
    print("="*60)
    print(f"📁 Data Directory: {DATA_DIR}")
    print(f"🌐 Frontend URL: {get_frontend_url()}/frontend/")
    print(f"🔧 Backend API: {get_backend_url()}")
    print("\n✅ Blockchain validation: Payment, tesSUCCESS, no DestinationTag, no Memos")
    print("="*60)
    create_frontend_index_html()
    app.run(debug=False, host='0.0.0.0', port=PORT)
