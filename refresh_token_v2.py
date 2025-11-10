#!/usr/bin/env python3
"""
SmartThings API Manager — Auto Token Refresh + Logging + SSL Verify=False
-------------------------------------------------------------------------
This script manages SmartThings OAuth2 tokens, refreshes them automatically,
logs all API requests/responses, and disables SSL verification (for testing).

⚠️ WARNING: verify=False is insecure and should only be used in trusted,
local, or controlled environments (e.g., emulator, localhost, internal testing).
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta
import urllib3

# Disable SSL warnings from urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================================
# =============== CONFIGURATION ============================
# ==========================================================

TOKEN_FILE = "token.txt"
TOKEN_URL = "https://auth-global.api.smartthings.com/oauth/token"
API_BASE = "https://api.smartthings.com/v1"
LOG_DIR = "logs"  # folder for API and token logs

os.makedirs(LOG_DIR, exist_ok=True)


# ==========================================================
# =============== FILE AND LOGGING HELPERS =================
# ==========================================================

def log_json(data, filename_prefix):
    """Writes dictionary to timestamped JSON log file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"{filename_prefix}_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"🪵 Logged: {path}")
    return path


def read_kv_file(path):
    """Reads key=value pairs into dictionary."""
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
    """Writes dictionary as key=value lines."""
    with open(path, "w", encoding="utf-8") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")


# ==========================================================
# =============== TOKEN MANAGEMENT =========================
# ==========================================================

def get_token_expiry(creds):
    """Returns datetime of token expiration or None if invalid."""
    try:
        updated = datetime.strptime(creds["updated_at"], "%Y-%m-%d %H:%M:%S")
        return updated + timedelta(seconds=int(creds["expires_in"]))
    except Exception:
        return None


def is_token_expired(creds):
    """Checks if the token is expired or near expiry."""
    expiry = get_token_expiry(creds)
    if expiry is None:
        return True
    remaining = (expiry - datetime.now()).total_seconds()
    print(f"⏱ Token expires in {int(remaining)} seconds.")
    return remaining < 60


def refresh_token(creds):
    """Performs SmartThings OAuth2 refresh_token grant."""
    print("🔁 Refreshing SmartThings token...")

    data = {
        "grant_type": "refresh_token",
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"]
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        # ⚠️ SSL verification disabled
        resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=False)
    except Exception as e:
        print(f"❌ Token request error: {e}")
        log_json({"error": str(e)}, "token_request_error")
        raise

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
        print("❌ Token refresh failed:", resp.status_code, resp.text)
        log_json({"status": resp.status_code, "text": resp.text}, "token_refresh_error")
        raise RuntimeError("Failed to refresh token")


def ensure_valid_token(creds):
    """Refreshes token automatically if expired."""
    if is_token_expired(creds):
        print("⚠️ Access token expired or missing — refreshing...")
        creds = refresh_token(creds)
    else:
        print("✅ Token still valid.")
    return creds


# ==========================================================
# =============== SMARTTHINGS API WRAPPERS =================
# ==========================================================

def safe_json(response):
    """Safely decode JSON; fallback to text."""
    try:
        return response.json()
    except Exception:
        return {"raw_text": response.text}


def api_request(method, path, creds, data=None, retry=True):
    """
    Performs a SmartThings API request with auto-refresh on 401.
    Logs every response for debugging.
    """
    creds = ensure_valid_token(creds)
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Content-Type": "application/json"
    }

    print(f"🌐 {method} {url}")
    try:
        # ⚠️ SSL verification disabled
        resp = requests.request(method, url, headers=headers, json=data, verify=False)
    except Exception as e:
        print(f"❌ Request error: {e}")
        log_json({"error": str(e)}, "request_error")
        return None

    if resp.status_code == 401 and retry:
        print("⚠️ Received 401 Unauthorized — refreshing token and retrying...")
        creds = refresh_token(creds)
        return api_request(method, path, creds, data, retry=False)

    # Log response (always)
    log_json({
        "url": url,
        "method": method,
        "status_code": resp.status_code,
        "response": safe_json(resp),
        "timestamp": datetime.now().isoformat()
    }, "api_response")

    if resp.status_code in (200, 201):
        print("✅ API request successful.")
        return safe_json(resp)
    else:
        print(f"❌ API request failed ({resp.status_code}).")
        print(resp.text)
        return None


def api_get(path, creds):
    """GET wrapper."""
    return api_request("GET", path, creds)


def api_post(path, data, creds):
    """POST wrapper."""
    return api_request("POST", path, creds)


# ==========================================================
# =============== MAIN EXAMPLE =============================
# ==========================================================

if __name__ == "__main__":
    try:
        creds = read_kv_file(TOKEN_FILE)

        # Example: GET devices
        devices = api_get("/devices", creds)
        if devices:
            print(f"Found {len(devices.get('items', []))} devices.")

        # Example: POST command to camera (e.g., take snapshot)
        # command_data = {
        #     "commands": [
        #         {"component": "main", "capability": "imageCapture", "command": "take"}
        #     ]
        # }
        # api_post(f"/devices/{device_id}/commands", command_data, creds)

    except Exception as e:
        print(f"⚠️ Fatal error: {e}")