import requests
import json
import os

# File paths
TOKEN_FILE = "token.txt"
OUTPUT_FILE = "smartthings_device_capabilities.json"

# Load token from file
def load_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"❌ Token file '{TOKEN_FILE}' not found.")
        exit(1)

ACCESS_TOKEN = load_token()

# Headers and URLs
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

base_url = "https://api.smartthings.com/v1"

def get_devices():
    url = f"{base_url}/devices"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("items", [])
    else:
        print(f"❌ Failed to fetch devices: {response.status_code}")
        return []

def get_device_capabilities(device_id):
    url = f"{base_url}/devices/{device_id}/components/main/capabilities"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"⚠️ Failed to fetch capabilities for device {device_id}: {response.status_code}")
        return []

def main():
    devices = get_devices()
    output_data = {}

    for device in devices:
        device_id = device.get("deviceId")
        device_name = device.get("label") or device.get("name")
        capabilities = get_device_capabilities(device_id)
        
        output_data[device_name] = {
            "deviceId": device_id,
            "capabilities": capabilities
        }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, indent=4)

    print(f"✅ Capabilities of {len(output_data)} devices saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
