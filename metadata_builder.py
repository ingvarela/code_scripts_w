import os
import csv
import json
import re

def cross_reference_files(image_folder, datasets_folder, output_csv):
    output_data = []

    # Regex to extract the numeric ID after 'chartqa_csv_file_'
    pattern = re.compile(r'chartqa_csv_file_(\d+)')

    for image_filename in os.listdir(image_folder):
        if not image_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue

        match = pattern.search(image_filename)
        if not match:
            print(f"⚠️ Skipping {image_filename}: no valid number found.")
            continue

        number = match.group(1)
        folder_name = f"chartqa_csv_file_{number}"
        subfolder_path = os.path.join(datasets_folder, folder_name)

        if not os.path.isdir(subfolder_path):
            print(f"❌ Folder not found for {folder_name}")
            continue

        # Construct expected CSV filename
        csv_filename = f"chartqa_csv_file.{number}.csv"
        csv_path = os.path.join(subfolder_path, csv_filename)

        if not os.path.exists(csv_path):
            print(f"❌ CSV not found: {csv_path}")
            continue

        # Read datapackage.json
        datapackage_path = os.path.join(subfolder_path, "datapackage.json")
        if not os.path.exists(datapackage_path):
            print(f"⚠️ datapackage.json missing for {folder_name}")
            continue

        try:
            with open(datapackage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name", "")
            link = data.get("link", "")
            retrieved_date = data.get("retrievedDate", "")
        except Exception as e:
            print(f"⚠️ Error reading JSON in {subfolder_path}: {e}")
            continue

        # Build absolute paths and append results
        image_path = os.path.abspath(os.path.join(image_folder, image_filename))
        csv_abs_path = os.path.abspath(csv_path)
        license_note = "CC BY Our World In Data"

        output_data.append([
            image_path, csv_abs_path, name, link, retrieved_date, license_note
        ])

    # Write results to CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Image Path", "CSV Path", "Name", "Link", "Retrieved Date", "License Note"])
        writer.writerows(output_data)

    print(f"✅ Done! {len(output_data)} matches saved to: {output_csv}")


# Example usage:
# cross_reference_files("path/to/images", "path/to/datasets", "output_metadata.csv")
