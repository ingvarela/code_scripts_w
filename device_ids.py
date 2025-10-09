import requests
import json

# Replace this with your SmartThings Personal Access Token
ACCESS_TOKEN = "YOUR_SMARTTHINGS_PAT_HERE"

# Output file
OUTPUT_FILE = "smartthings_device_ids.txt"

# Headers for SmartThings API request
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# API endpoint to list devices
url = "https://api.smartthings.com/v1/devices"

def fetch_device_ids():
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        devices = response.json().get("items", [])
        device_ids = [device.get("deviceId") for device in devices]
        
        # Write device IDs to file
        with open(OUTPUT_FILE, "w") as f:
            for device_id in device_ids:
                f.write(device_id + "\n")
        
        print(f"✅ {len(device_ids)} device IDs saved to {OUTPUT_FILE}")
    else:
        print(f"❌ Failed to fetch devices. Status code: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    fetch_device_ids()
