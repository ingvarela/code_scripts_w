#!/usr/bin/env python3
"""
Cross-match image paths across three sources:
1. A folder containing images
2. A CSV file (with a specified column)
3. A JSON file (field: "image")

Outputs:
  - match_summary.csv   → Shows presence across all sources
  - match_report.txt    → Readable summary with counts
  - matched_only.csv    → Files present in all three

Default paths are provided for convenience — modify as needed.
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
    return set(df[column].dropna().apply(normalize_filename))


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


def generate_report(folder_set, csv_set, json_set, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    all_files = folder_set | csv_set | json_set
    records = []

    for f in sorted(all_files):
        records.append({
            "Filename": f,
            "In_Folder": f in folder_set,
            "In_CSV": f in csv_set,
            "In_JSON": f in json_set
        })

    df = pd.DataFrame(records)
    df["All_Present"] = df[["In_Folder", "In_CSV", "In_JSON"]].all(axis=1)

    # Save summary CSVs
    summary_csv = os.path.join(output_dir, "match_summary.csv")
    matched_only_csv = os.path.join(output_dir, "matched_only.csv")
    df.to_csv(summary_csv, index=False)
    df[df["All_Present"]].to_csv(matched_only_csv, index=False)

    # Prepare log report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_path = os.path.join(output_dir, "match_report.txt")

    total = len(df)
    all_present = df["All_Present"].sum()
    missing_any = total - all_present

    missing_csv = df[~df["In_CSV"]]["Filename"].tolist()
    missing_json = df[~df["In_JSON"]]["Filename"].tolist()
    missing_folder = df[~df["In_Folder"]]["Filename"].tolist()

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== CROSS-SOURCE IMAGE MATCH REPORT ===\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"Total unique filenames across all sources: {total}\n")
        f.write(f"Present in all three: {all_present}\n")
        f.write(f"Missing from at least one: {missing_any}\n\n")

        if missing_folder:
            f.write(f"❌ Missing from folder ({len(missing_folder)}):\n")
            for name in missing_folder[:10]:
                f.write(f" - {name}\n")
            if len(missing_folder) > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        if missing_csv:
            f.write(f"❌ Missing from CSV ({len(missing_csv)}):\n")
            for name in missing_csv[:10]:
                f.write(f" - {name}\n")
            if len(missing_csv) > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        if missing_json:
            f.write(f"❌ Missing from JSON ({len(missing_json)}):\n")
            for name in missing_json[:10]:
                f.write(f" - {name}\n")
            if len(missing_json) > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        f.write(f"✅ Full results saved to: {summary_csv}\n")
        f.write(f"✅ Fully matched only: {matched_only_csv}\n")

    print(f"\n✅ Matching complete.")
    print(f"  Total files: {total}")
    print(f"  All present: {all_present}")
    print(f"  Missing (any): {missing_any}")
    print(f"  Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Match images across folder, CSV, and JSON sources.")
    parser.add_argument("--folder", default="C:/Users/svs26/Desktop/images", help="Path to folder containing images.")
    parser.add_argument("--csv", default="C:/Users/svs26/Desktop/input.csv", help="Path to CSV file.")
    parser.add_argument("--column", default="Image Path", help="Column name in CSV containing image paths/names.")
    parser.add_argument("--json", default="C:/Users/svs26/Desktop/input.json", help="Path to JSON file with 'image' field.")
    parser.add_argument("--out", default="C:/Users/svs26/Desktop/output", help="Output directory for reports.")

    args = parser.parse_args()

    folder_set = set(os.listdir(args.folder))
    csv_set = load_csv(args.csv, args.column)
    json_set = load_json(args.json)

    generate_report(folder_set, csv_set, json_set, args.out)


if __name__ == "__main__":
    main()