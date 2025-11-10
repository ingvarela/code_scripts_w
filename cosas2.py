#!/usr/bin/env python3
"""
SmartThings Token Manager — Forced Periodic Refresh (Basic Auth)
----------------------------------------------------------------
✓ Always refreshes tokens every X minutes, even if still valid
✓ Uses Basic Auth (client_id:client_secret)
✓ Verifies token.txt overwrite after each run
✓ Keeps full logs and a human-readable history file
"""

import base64, requests, json, os, time, shutil, urllib3
from datetime import datetime

# ==========================================================
# CONFIGURATION
# ==========================================================
TOKEN_FILE   = "token.txt"
BACKUP_DIR   = "backups"
LOG_DIR      = "logs"
HISTORY_LOG  = "token_refresh_history.log"

TOKEN_URL    = "https://auth-global.api.smartthings.com/oauth/token"
REFRESH_INTERVAL_MINUTES = 60   # ⏱ refresh every X minutes
VERIFY_SSL   = False            # ⚠️ True for production

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================================
# UTILITIES
# ==========================================================
def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def backup_file(path):
    if os.path.exists(path):
        dst = os.path.join(BACKUP_DIR, f"token_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
        shutil.copy2(path, dst)
        print(f"🗃️  Backup saved: {dst}")

def log_json(data, prefix):
    path = os.path.join(LOG_DIR, f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"🪵 Log saved: {path}")

def append_history(entry):
    with open(HISTORY_LOG, "a", encoding="utf-8") as f:
        f.write(f"{timestamp()} — {entry}\n")

def read_kv_file(path):
    creds = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k,v=line.strip().split("=",1)
                creds[k.strip()]=v.strip()
    return creds

def verify_write(path, data):
    """Verify that the write was successful."""
    try:
        reloaded = read_kv_file(path)
        if reloaded.get("access_token") == data.get("access_token"):
            append_history("✅ Verified token.txt overwrite succeeded.")
            return True
        else:
            append_history("⚠️ Verification mismatch after write.")
            return False
    except Exception as e:
        append_history(f"❌ token.txt verify error: {e}")
        return False

def write_kv_file(path, data):
    """Write safely and verify overwrite."""
    backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")

    if verify_write(path, data):
        print(f"💾 Verified: {path} updated successfully.")
    else:
        print(f"⚠️ token.txt overwrite verification failed.")

def safe_json(resp):
    try: return resp.json()
    except Exception: return {"raw": resp.text}


# ==========================================================
# TOKEN REFRESH (FORCED)
# ==========================================================
def make_basic_header(client_id, client_secret):
    token = f"{client_id}:{client_secret}"
    b64 = base64.b64encode(token.encode()).decode()
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

def refresh_token(creds):
    """Always refresh the token, even if still valid."""
    print("🔁 Performing SmartThings token refresh (forced).")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"]
    }
    headers = make_basic_header(creds["client_id"], creds["client_secret"])
    resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=VERIFY_SSL)

    log_json({
        "method": "POST", "url": TOKEN_URL,
        "data": data, "status": resp.status_code,
        "response": safe_json(resp)
    }, "token_refresh_request")

    if resp.status_code == 200:
        tokens = resp.json()
        creds.update({
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", creds.get("refresh_token")),
            "expires_in": str(tokens.get("expires_in", "86400")),
            "updated_at": timestamp()
        })
        write_kv_file(TOKEN_FILE, creds)
        append_history("✅ Forced token refresh and overwrite verified.")
        print("✅ Token refresh and overwrite verified.")
    else:
        append_history(f"❌ Refresh failed ({resp.status_code}) — {resp.text[:120]}")
        print(f"❌ Refresh failed ({resp.status_code}): {resp.text}")

    return creds


# ==========================================================
# SCHEDULER LOOP
# ==========================================================
def run_scheduler():
    print(f"🕒 SmartThings Forced Token Refresher running — every {REFRESH_INTERVAL_MINUTES} min")
    append_history("▶️  Token refresher service started.")

    while True:
        try:
            creds = read_kv_file(TOKEN_FILE)
            refresh_token(creds)
        except Exception as e:
            msg = f"⚠️ Error during refresh: {e}"
            print(msg)
            append_history(msg)

        print(f"⏳ Sleeping {REFRESH_INTERVAL_MINUTES} minutes...\n")
        time.sleep(REFRESH_INTERVAL_MINUTES * 60)


# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("\n🛑 Stopped manually.")
        append_history("🛑 Token refresher stopped manually.")