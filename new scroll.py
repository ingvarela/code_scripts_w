#!/usr/bin/env python3
"""
SmartThings Token Manager — Final Version
-----------------------------------------
✓ Exchanges authorization_code → access/refresh tokens
✓ Refreshes tokens automatically (no client_secret required)
✓ Logs full requests & responses
✓ Creates timestamped backups of token.txt
✓ Can safely use verify=False for local testing
"""

import requests
import json
import os
import time
import shutil
import urllib3
from datetime import datetime, timedelta

# ==========================================================
# CONFIGURATION
# ==========================================================
TOKEN_FILE = "token.txt"
BACKUP_DIR = "backups"
LOG_DIR = "logs"
TOKEN_URL = "https://auth-global.api.smartthings.com/oauth/token"
API_BASE = "https://api.smartthings.com/v1"
VERIFY_SSL = False  # ⚠️ Set to True in production

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Disable SSL warnings if verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==========================================================
# UTILITIES
# ==========================================================
def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_file(path):
    """Back up token.txt before any overwrite."""
    if os.path.exists(path):
        dst = os.path.join(BACKUP_DIR, f"token_{timestamp()}.bak")
        shutil.copy2(path, dst)
        print(f"🗃️  Backup saved: {dst}")


def log_json(data, prefix):
    """Write structured log JSON."""
    path = os.path.join(LOG_DIR, f"{prefix}_{timestamp()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"🪵 Log saved: {path}")


def read_kv_file(path):
    """Read token.txt into dictionary."""
    creds = {}
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing token file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k.strip()] = v.strip()
    return creds


def write_kv_file(path, data):
    """Write token.txt safely with backup."""
    backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")
    print(f"💾 Updated {path}")


# ==========================================================
# TOKEN MANAGEMENT (no client_secret)
# ==========================================================
def exchange_code_for_tokens(creds):
    """Exchange authorization_code for access/refresh tokens."""
    print("🔑 Exchanging authorization code for new tokens...")

    data = {
        "grant_type": "authorization_code",
        "client_id": creds["client_id"],
        "code": creds["authorization_code"],
        "redirect_uri": creds["redirect_uri"],
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=VERIFY_SSL)

    if resp.status_code == 200:
        tokens = resp.json()
        print("✅ Token exchange successful.")
        log_json(tokens, "token_exchange")

        creds.pop("authorization_code", None)
        creds.update({
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "expires_in": str(tokens.get("expires_in", "86400")),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        })
        write_kv_file(TOKEN_FILE, creds)
        return creds
    else:
        print(f"❌ Exchange failed ({resp.status_code}): {resp.text}")
        log_json({"status": resp.status_code, "text": resp.text}, "token_exchange_error")
        raise RuntimeError("Failed to exchange authorization code")


def refresh_token(creds):
    """Refresh expired access token (no client_secret required)."""
    print("🔁 Refreshing SmartThings token...")

    data = {
        "grant_type": "refresh_token",
        "client_id": creds["client_id"],
        "refresh_token": creds["refresh_token"]
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=VERIFY_SSL)

    if resp.status_code == 200:
        tokens = resp.json()
        print("✅ Token refresh successful.")
        log_json(tokens, "token_refresh")

        creds.update({
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", creds.get("refresh_token")),
            "expires_in": str(tokens.get("expires_in", "86400")),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        })
        write_kv_file(TOKEN_FILE, creds)
        return creds
    else:
        print(f"❌ Refresh failed ({resp.status_code}): {resp.text}")
        log_json({"status": resp.status_code, "text": resp.text}, "token_refresh_error")
        raise RuntimeError("Failed to refresh token")


def get_token_expiry(creds):
    try:
        updated = datetime.strptime(creds["updated_at"], "%Y-%m-%d %H:%M:%S")
        return updated + timedelta(seconds=int(creds["expires_in"]))
    except Exception:
        return None


def is_token_expired(creds):
    expiry = get_token_expiry(creds)
    if not expiry:
        return True
    remaining = (expiry - datetime.now()).total_seconds()
    print(f"⏱ Token expires in {int(remaining)} seconds.")
    return remaining < 60


def ensure_valid_token(creds):
    """Ensure token validity; handle exchange and refresh automatically."""
    if "authorization_code" in creds and "access_token" not in creds:
        creds = exchange_code_for_tokens(creds)
    elif is_token_expired(creds):
        creds = refresh_token(creds)
    else:
        print("✅ Token valid.")
    return creds


# ==========================================================
# API REQUEST WRAPPERS (full logging)
# ==========================================================
def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def api_request(method, path, creds, data=None, retry=True):
    """Perform SmartThings API request with full logging."""
    creds = ensure_valid_token(creds)
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Content-Type": "application/json"
    }

    print(f"\n🌐 [{method}] Request URL: {url}")
    if data:
        print(f"📤 Request Body:\n{json.dumps(data, indent=2)}")

    start = time.time()
    try:
        resp = requests.request(method, url, headers=headers, json=data, verify=VERIFY_SSL)
    except Exception as e:
        print(f"❌ Request error: {e}")
        log_json({"error": str(e), "method": method, "url": url}, "request_error")
        return None

    duration_ms = int((time.time() - start) * 1000)
    resp_json = safe_json(resp)
    print(f"📥 Response Status: {resp.status_code} ({duration_ms} ms)")
    print(f"📩 Full Response:\n{json.dumps(resp_json, indent=2)}")

    log_json({
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "url": url,
        "headers": headers,
        "payload": data if data else {},
        "status_code": resp.status_code,
        "response_time_ms": duration_ms,
        "response": resp_json
    }, "api_request_full")

    if resp.status_code == 401 and retry:
        print("⚠️ 401 Unauthorized — refreshing and retrying...")
        creds = refresh_token(creds)
        return api_request(method, path, creds, data, retry=False)

    return resp_json


def api_get(path, creds):
    return api_request("GET", path, creds)


def api_post(path, data, creds):
    return api_request("POST", path, creds)


# ==========================================================
# MAIN EXECUTION
# ==========================================================
if __name__ == "__main__":
    try:
        creds = read_kv_file(TOKEN_FILE)
        creds = ensure_valid_token(creds)

        # Example: GET devices
        devices = api_get("/devices", creds)
        if devices and "items" in devices:
            print(f"📦 Found {len(devices['items'])} devices.")

        # Example: send a command
        # command = {
        #     "commands": [
        #         {"component": "main", "capability": "imageCapture", "command": "take"}
        #     ]
        # }
        # api_post(f"/devices/{device_id}/commands", command, creds)

    except Exception as e:
        print(f"⚠️ Fatal error: {e}")