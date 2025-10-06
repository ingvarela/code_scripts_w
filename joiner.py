
#!/usr/bin/env python3
"""
Sequential JSON joiner (outputs one combined .json file)
--------------------------------------------------------
- Asks for a folder path containing .json files
- Reads each JSON file in alphabetical order
- Joins all into a single list-based JSON file
- Saves the merged file in the same folder as 'joined_all.json'
"""

import os
import json

def join_jsons_in_folder(folder_path):
    if not os.path.isdir(folder_path):
        print(f"❌ Invalid folder path: {folder_path}")
        return

    json_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(".json")])
    if not json_files:
        print("⚠️ No .json files found in this folder.")
        return

    combined_data = []

    for file_name in json_files:
        file_path = os.path.join(folder_path, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # If JSON is a list, extend; if it's an object, append
                if isinstance(data, list):
                    combined_data.extend(data)
                else:
                    combined_data.append(data)
            print(f"✓ Added {file_name}")
        except Exception as e:
            print(f"⚠️ Skipped {file_name}: {e}")

    output_path = os.path.join(folder_path, "joined_all.json")
    with open(output_path, "w", encoding="utf-8") as out_file:
        json.dump(combined_data, out_file, indent=2, ensure_ascii=False)

    print(f"\n✅ Merged {len(json_files)} files into:")
    print(f"   {output_path}")
    print(f"📦 Total items: {len(combined_data)}")


if __name__ == "__main__":
    print("📂 Enter or drag the folder path containing the JSON files:")
    folder_path = input("Folder path: ").strip().strip('"')
    join_jsons_in_folder(folder_path)