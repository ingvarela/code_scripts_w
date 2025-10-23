#!/usr/bin/env python3
"""
Verify that every image listed in a metadata CSV exists in both:
1. The JSON file (field: "image")
2. The image folder

Treats the CSV as the "source of truth".

Outputs:
  - verification_summary.csv  → Shows for each metadata entry if it exists in JSON/folder
  - missing_from_json.csv     → Images missing in JSON
  - missing_from_folder.csv   → Images missing in folder
  - verification_report.txt   → Readable text summary
"""

import os
import json
import argparse
import pandas as pd
from datetime import datetime


def normalize_filename(path):
    """Return only the basename (filename) for comparison."""
    return os.path.basename(str(path).strip())


def load_csv(csv_path, column):
    df = pd.read_csv(csv_path)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in CSV. Found: {list(df.columns)}")
    return list(df[column].dropna().apply(normalize_filename))


def load_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    images = []
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and "image" in entry:
                images.append(normalize_filename(entry["image"]))
    else:
        raise ValueError("JSON root must be a list of objects with 'image' fields.")
    return set(images)


def verify_metadata(csv_list, folder_set, json_set, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    records = []
    missing_json, missing_folder = [], []

    for fname in csv_list:
        in_json = fname in json_set
        in_folder = fname in folder_set
        records.append({
            "Filename": fname,
            "In_Metadata": True,
            "In_JSON": in_json,
            "In_Folder": in_folder,
            "All_Present": in_json and in_folder
        })

        if not in_json:
            missing_json.append(fname)
        if not in_folder:
            missing_folder.append(fname)

    df = pd.DataFrame(records)

    # Save results
    summary_csv = os.path.join(output_dir, "verification_summary.csv")
    missing_json_csv = os.path.join(output_dir, "missing_from_json.csv")
    missing_folder_csv = os.path.join(output_dir, "missing_from_folder.csv")

    df.to_csv(summary_csv, index=False)
    pd.DataFrame({"Missing_From_JSON": missing_json}).to_csv(missing_json_csv, index=False)
    pd.DataFrame({"Missing_From_Folder": missing_folder}).to_csv(missing_folder_csv, index=False)

    # Generate readable report
    report_path = os.path.join(output_dir, "verification_report.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = len(csv_list)
    complete = df["All_Present"].sum()
    missing_any = total - complete

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== METADATA SOURCE VERIFICATION REPORT ===\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"Total metadata entries: {total}\n")
        f.write(f"Fully matched (in all sources): {complete}\n")
        f.write(f"Missing from at least one source: {missing_any}\n\n")

        if missing_folder:
            f.write(f"❌ Missing from folder ({len(missing_folder)}):\n")
            for name in missing_folder[:10]:
                f.write(f" - {name}\n")
            if len(missing_folder) > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        if missing_json:
            f.write(f"❌ Missing from JSON ({len(missing_json)}):\n")
            for name in missing_json[:10]:
                f.write(f" - {name}\n")
            if len(missing_json) > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        f.write(f"✅ Detailed summary saved to: {summary_csv}\n")
        f.write(f"✅ Missing JSON list: {missing_json_csv}\n")
        f.write(f"✅ Missing folder list: {missing_folder_csv}\n")

    print(f"\n✅ Verification complete.")
    print(f"  Total metadata entries: {total}")
    print(f"  All present: {complete}")
    print(f"  Missing (any): {missing_any}")
    print(f"  Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Verify that all metadata CSV images exist in JSON and folder.")
    parser.add_argument("--folder", default="C:/Users/svs26/Desktop/images", help="Path to image folder.")
    parser.add_argument("--csv", default="C:/Users/svs26/Desktop/input.csv", help="Metadata CSV path.")
    parser.add_argument("--column", default="Image Path", help="CSV column containing image paths/names.")
    parser.add_argument("--json", default="C:/Users/svs26/Desktop/input.json", help="JSON file with 'image' field.")
    parser.add_argument("--out", default="C:/Users/svs26/Desktop/output", help="Output folder for reports.")

    args = parser.parse_args()

    # Load sources
    folder_set = set(os.listdir(args.folder))
    csv_list = load_csv(args.csv, args.column)
    json_set = load_json(args.json)

    verify_metadata(csv_list, folder_set, json_set, args.out)


if __name__ == "__main__":
    main()