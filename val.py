#!/usr/bin/env python3
"""
Match filenames listed in a CSV against actual files in a folder.

- Supports both full paths and filename-only CSV entries.
- Outputs:
    1. matched_files.csv  — found matches
    2. missing_files.csv  — not found
    3. match_report.txt   — summary log

Usage:
    python match_filenames_with_csv.py --csv input.csv --folder /path/to/images --column "Image Path"
"""

import os
import csv
import argparse
import pandas as pd
from datetime import datetime


def match_filenames(csv_path, folder_path, column_name, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_csv(csv_path)

    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found in CSV: {list(df.columns)}")

    # Collect filenames in the target folder
    all_files_in_folder = set(os.listdir(folder_path))
    matched, missing = [], []

    # Iterate over CSV entries
    for value in df[column_name].dropna():
        value_str = str(value).strip()
        filename = os.path.basename(value_str)

        if filename in all_files_in_folder:
            matched.append({
                "CSV Entry": value_str,
                "Matched File": os.path.join(folder_path, filename)
            })
        else:
            missing.append({
                "CSV Entry": value_str,
                "Expected Path": os.path.join(folder_path, filename)
            })

    # Save results to CSVs
    matched_df = pd.DataFrame(matched)
    missing_df = pd.DataFrame(missing)

    matched_out = os.path.join(output_dir, "matched_files.csv")
    missing_out = os.path.join(output_dir, "missing_files.csv")
    report_out = os.path.join(output_dir, "match_report.txt")

    matched_df.to_csv(matched_out, index=False)
    missing_df.to_csv(missing_out, index=False)

    # --- Generate summary report ---
    total_entries = len(df[column_name].dropna())
    matched_count = len(matched)
    missing_count = len(missing)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(report_out, "w", encoding="utf-8") as f:
        f.write("=== FILE MATCH REPORT ===\n")
        f.write(f"Generated: {timestamp}\n")
        f.write(f"CSV Source: {csv_path}\n")
        f.write(f"Folder Checked: {folder_path}\n\n")
        f.write(f"Total Entries in CSV: {total_entries}\n")
        f.write(f"Matched Files: {matched_count}\n")
        f.write(f"Missing Files: {missing_count}\n\n")

        if missing_count > 0:
            f.write("⚠️  Missing Files (showing up to 10):\n")
            for item in missing[:10]:
                f.write(f" - {item['CSV Entry']}\n")
        else:
            f.write("✅ No missing files detected.\n")

        f.write("\nDetails saved to:\n")
        f.write(f"  Matched: {matched_out}\n")
        f.write(f"  Missing: {missing_out}\n")

    print(f"\n✅ Match completed.")
    print(f"  Matched files: {matched_count}")
    print(f"  Missing files: {missing_count}")
    print(f"  Report saved to: {report_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Match filenames in a CSV with actual files in a folder.")
    parser.add_argument("--csv", required=True, help="Path to the input CSV file")
    parser.add_argument("--folder", required=True, help="Path to the folder containing images/files")
    parser.add_argument("--column", required=True, help="Name of the column in the CSV that contains file paths or names")
    parser.add_argument("--out", default=".", help="Output directory for result CSVs and report")

    args = parser.parse_args()

    match_filenames(args.csv, args.folder, args.column, args.out)
