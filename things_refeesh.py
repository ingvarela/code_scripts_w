#!/usr/bin/env python3
"""
SmartThings Token Manager — Basic-Auth Version
----------------------------------------------
✓ Reads authorization_code from token.txt
✓ Uses HTTP Basic Auth for both code-exchange and refresh
✓ Automatically refreshes tokens
✓ Full request/response logging + token backups
✓ verify=False toggle for local testing
"""

import base64, requests, json, os, time, shutil, urllib3
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
TOKEN_FILE = "token.txt"
BACKUP_DIR = "backups"
LOG_DIR   = "logs"
TOKEN_URL = "https://auth-global.api.smartthings.com/oauth/token"
API_BASE  = "https://api.smartthings.com/v1"
VERIFY_SSL = False        # ⚠️ Set True in production
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def timestamp(): return datetime.now().strftime("%Y%m%d_%H%M%S")

def backup_file(path):
    if os.path.exists(path):
        dst = os.path.join(BACKUP_DIR, f"token_{timestamp()}.bak")
        shutil.copy2(path, dst)
        print(f"🗃️  Backup saved: {dst}")

def log_json(data, prefix):
    path = os.path.join(LOG_DIR, f"{prefix}_{timestamp()}.json")
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
    print(f"🪵 Log saved: {path}")

def read_kv_file(path):
    creds = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k,v=line.strip().split("=",1); creds[k.strip()]=v.strip()
    return creds

def write_kv_file(path, data):
    backup_file(path)
    with open(path,"w",encoding="utf-8") as f:
        for k,v in data.items(): f.write(f"{k}={v}\n")
    print(f"💾 Updated {path}")

def safe_json(resp):
    try: return resp.json()
    except Exception: return {"raw": resp.text}

# ---------------------------------------------------------------------
# Token handling (Basic-Auth)
# ---------------------------------------------------------------------
def make_basic_header(client_id, client_secret):
    token = f"{client_id}:{client_secret}"
    b64   = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {b64}",
            "Content-Type": "application/x-www-form-urlencoded"}

def exchange_code_for_tokens(creds):
    print("🔑 Exchanging authorization_code from token.txt (Basic Auth)...")

    data = {
        "grant_type": "authorization_code",
        "code": creds["authorization_code"],
        "redirect_uri": creds.get("redirect_uri","")
    }
    headers = make_basic_header(creds["client_id"], creds["client_secret"])
    resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=VERIFY_SSL)

    log_json({"url":TOKEN_URL,"method":"POST","data":data,
              "status":resp.status_code,"response":safe_json(resp)},
             "token_exchange_request")

    if resp.status_code==200:
        tokens = resp.json()
        print("✅ Token exchange successful.")
        creds.update({
            "access_token":tokens.get("access_token",""),
            "refresh_token":tokens.get("refresh_token",""),
            "expires_in":str(tokens.get("expires_in","86400")),
            "updated_at":time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
        })
        write_kv_file(TOKEN_FILE,creds)
        return creds
    else:
        print(f"❌ Exchange failed ({resp.status_code}): {resp.text}")
        raise RuntimeError("Failed to exchange authorization_code")

def refresh_token(creds):
    print("🔁 Refreshing token (Basic Auth)...")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"]
    }
    headers = make_basic_header(creds["client_id"], creds["client_secret"])
    resp = requests.post(TOKEN_URL, data=data, headers=headers, verify=VERIFY_SSL)

    log_json({"url":TOKEN_URL,"method":"POST","data":data,
              "status":resp.status_code,"response":safe_json(resp)},
             "token_refresh_request")

    if resp.status_code==200:
        tokens = resp.json()
        print("✅ Token refresh successful.")
        creds.update({
            "access_token":tokens.get("access_token",""),
            "refresh_token":tokens.get("refresh_token",creds.get("refresh_token")),
            "expires_in":str(tokens.get("expires_in","86400")),
            "updated_at":time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
        })
        write_kv_file(TOKEN_FILE,creds)
        return creds
    else:
        print(f"❌ Refresh failed ({resp.status_code}): {resp.text}")
        raise RuntimeError("Failed to refresh token")

def get_token_expiry(creds):
    try:
        updated=datetime.strptime(creds["updated_at"],"%Y-%m-%d %H:%M:%S")
        return updated+timedelta(seconds=int(creds["expires_in"]))
    except Exception: return None

def is_token_expired(creds):
    expiry=get_token_expiry(creds)
    if not expiry: return True
    remaining=(expiry-datetime.now()).total_seconds()
    print(f"⏱ Token expires in {int(remaining)} seconds.")
    return remaining<60

def ensure_valid_token(creds):
    if "access_token" not in creds and "authorization_code" in creds:
        creds = exchange_code_for_tokens(creds)
    elif is_token_expired(creds):
        creds = refresh_token(creds)
    else:
        print("✅ Token valid.")
    return creds

# ---------------------------------------------------------------------
# SmartThings API requests
# ---------------------------------------------------------------------
def api_request(method, path, creds, data=None, retry=True):
    creds = ensure_valid_token(creds)
    url   = f"{API_BASE}{path}"
    headers = {"Authorization":f"Bearer {creds['access_token']}",
               "Content-Type":"application/json"}

    print(f"\n🌐 [{method}] {url}")
    if data: print("📤 Body:\n",json.dumps(data,indent=2))
    start=time.time()
    resp=requests.request(method,url,headers=headers,json=data,verify=VERIFY_SSL)
    dur=int((time.time()-start)*1000)
    body=safe_json(resp)
    print(f"📥 {resp.status_code} ({dur} ms)")
    print(json.dumps(body,indent=2))

    log_json({"timestamp":datetime.now().isoformat(),
              "method":method,"url":url,"headers":headers,
              "payload":data if data else {},"status":resp.status_code,
              "response_time_ms":dur,"response":body},"api_request_full")

    if resp.status_code==401 and retry:
        print("⚠️ 401 Unauthorized → refreshing token and retrying…")
        creds = refresh_token(creds)
        return api_request(method,path,creds,data,False)
    return body

def api_get(path,creds):  return api_request("GET",path,creds)
def api_post(path,data,creds): return api_request("POST",path,creds)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__=="__main__":
    try:
        creds = read_kv_file(TOKEN_FILE)
        creds = ensure_valid_token(creds)

        devices = api_get("/devices", creds)
        if devices and "items" in devices:
            print(f"📦 Found {len(devices['items'])} devices.")

        # Example POST command:
        # cmd={"commands":[{"component":"main","capability":"imageCapture","command":"take"}]}
        # api_post(f"/devices/{device_id}/commands",cmd,creds)

    except Exception as e:
        print(f"⚠️ Error: {e}")