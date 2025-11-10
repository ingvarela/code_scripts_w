def api_request(method, path, creds, data=None, retry=True):
    """Perform a SmartThings API request and log full request + response details."""
    creds = ensure_valid_token(creds)
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Content-Type": "application/json"
    }

    # === Print to console for visibility ===
    print(f"\n🌐 [{method}] Request URL: {url}")
    if data:
        print(f"📤 Request Body:\n{json.dumps(data, indent=2)}")

    start_time = time.time()
    try:
        resp = requests.request(method, url, headers=headers, json=data, verify=VERIFY_SSL)
    except Exception as e:
        print(f"❌ Request error: {e}")
        log_json({"error": str(e), "method": method, "url": url}, "request_error")
        return None

    duration_ms = int((time.time() - start_time) * 1000)
    resp_text = None
    try:
        resp_json = resp.json()
        resp_text = json.dumps(resp_json, indent=2)
    except Exception:
        resp_json = {"raw": resp.text}
        resp_text = resp.text

    # === Print full response ===
    print(f"📥 Response Status: {resp.status_code} ({duration_ms} ms)")
    print(f"📩 Full Response:\n{resp_text}")

    # === Log to file ===
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "url": url,
        "headers": headers,
        "payload": data if data else {},
        "status_code": resp.status_code,
        "response_time_ms": duration_ms,
        "response": resp_json
    }
    log_json(log_entry, "api_request_full")

    # === Handle expired tokens ===
    if resp.status_code == 401 and retry:
        print("⚠️ 401 Unauthorized — refreshing and retrying...")
        creds = refresh_token(creds)
        return api_request(method, path, creds, data, retry=False)

    if resp.ok:
        print("✅ Request successful.")
        return resp_json
    else:
        print(f"❌ Request failed ({resp.status_code}).")
        return resp_json