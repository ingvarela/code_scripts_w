#!/usr/bin/env python3
"""
Compare filenames in a metadata CSV with actual files in a folder.

Outputs:
  - matched_files.csv          → Found in both folder and metadata
  - missing_from_folder.csv    → Present in CSV but not found in folder
  - extra_in_folder.csv        → Present in folder but not listed in CSV
  - match_report.txt           → Readable text summary

Supports full or relative paths in the CSV column.
"""

import os
import argparse
import pandas as pd
from datetime import datetime


def normalize_filename(path):
    """Extract only the filename from any given path."""
    return os.path.basename(str(path).strip())


def compare_folder_with_metadata(csv_path, folder_path, column_name, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)

    # --- Load data
    df = pd.read_csv(csv_path)
    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found in CSV. Found: {list(df.columns)}")

    csv_filenames = set(df[column_name].dropna().apply(normalize_filename))
    folder_filenames = set(os.listdir(folder_path))

    # --- Comparisons
    matched = sorted(csv_filenames & folder_filenames)
    missing = sorted(csv_filenames - folder_filenames)
    extra = sorted(folder_filenames - csv_filenames)

    # --- Save outputs
    matched_csv = os.path.join(output_dir, "matched_files.csv")
    missing_csv = os.path.join(output_dir, "missing_from_folder.csv")
    extra_csv = os.path.join(output_dir, "extra_in_folder.csv")
    report_txt = os.path.join(output_dir, "match_report.txt")

    pd.DataFrame({"Matched": matched}).to_csv(matched_csv, index=False)
    pd.DataFrame({"Missing_From_Folder": missing}).to_csv(missing_csv, index=False)
    pd.DataFrame({"Extra_In_Folder": extra}).to_csv(extra_csv, index=False)

    # --- Generate report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_csv = len(csv_filenames)
    total_folder = len(folder_filenames)
    matched_count = len(matched)
    missing_count = len(missing)
    extra_count = len(extra)

    with open(report_txt, "w", encoding="utf-8") as f:
        f.write("=== FOLDER vs METADATA COMPARISON REPORT ===\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"CSV Source: {csv_path}\n")
        f.write(f"Image Folder: {folder_path}\n\n")
        f.write(f"Total entries in metadata: {total_csv}\n")
        f.write(f"Total files in folder: {total_folder}\n")
        f.write(f"Matched: {matched_count}\n")
        f.write(f"Missing from folder: {missing_count}\n")
        f.write(f"Extra in folder: {extra_count}\n\n")

        if missing_count > 0:
            f.write("⚠️ Missing files (in CSV but not in folder):\n")
            for item in missing[:10]:
                f.write(f" - {item}\n")
            if missing_count > 10:
                f.write("   ... (truncated)\n")
            f.write("\n")

        if extra_count > 0:
            f.write("⚠️ Extra files (in folder but not in CSV):\n")
            for item in extra[:10]:
                f.write(f" - {item}\n")
            if extra_count > 10:
                f.write("   ... (truncated)\n")

        f.write("\n✅ Detailed results saved to:\n")
        f.write(f"  {matched_csv}\n  {missing_csv}\n  {extra_csv}\n")

    print(f"\n✅ Comparison complete.")
    print(f"  Matched: {matched_count}")
    print(f"  Missing from folder: {missing_count}")
    print(f"  Extra in folder: {extra_count}")
    print(f"  Report saved to: {report_txt}")


def main():
    parser = argparse.ArgumentParser(description="Compare image folder with metadata CSV.")
    parser.add_argument("--folder", default="C:/Users/svs26/Desktop/images", help="Path to image folder.")
    parser.add_argument("--csv", default="C:/Users/svs26/Desktop/input.csv", help="Path to metadata CSV.")
    parser.add_argument("--column", default="Image Path", help="Column name in the CSV that lists image paths/names.")
    parser.add_argument("--out", default="C:/Users/svs26/Desktop/output", help="Output directory for results.")
    args = parser.parse_args()

    compare_folder_with_metadata(args.csv, args.folder, args.column, args.out)


if __name__ == "__main__":
    main()