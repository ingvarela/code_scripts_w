#!/usr/bin/env python3
"""
Strict verification between a metadata CSV and an image folder.

Checks for:
  - Files present in both (perfect matches)
  - Files missing from the folder (listed in CSV but not found)
  - Extra files in the folder (not listed in CSV)

Outputs:
  - matched_files.csv
  - missing_from_folder.csv
  - extra_in_folder.csv
  - match_report.txt
"""

import os
import argparse
import pandas as pd
from datetime import datetime


def normalize_filename(path):
    """Extract only the filename (no directory) and standardize case."""
    return os.path.basename(str(path).strip()).lower()


def verify_folder_and_metadata(csv_path, folder_path, column_name, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)

    # --- Load CSV metadata
    df = pd.read_csv(csv_path)
    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found in CSV. Found: {list(df.columns)}")

    csv_filenames = set(df[column_name].dropna().apply(normalize_filename))
    folder_filenames = set(normalize_filename(f) for f in os.listdir(folder_path))

    # --- Compare
    matched = sorted(csv_filenames & folder_filenames)
    missing = sorted(csv_filenames - folder_filenames)
    extra = sorted(folder_filenames - csv_filenames)

    # --- Save results
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
    perfect_match = (missing_count == 0 and extra_count == 0)

    with open(report_txt, "w", encoding="utf-8") as f:
        f.write("=== STRICT FOLDER ↔ METADATA VERIFICATION REPORT ===\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"CSV Source: {csv_path}\n")
        f.write(f"Folder Checked: {folder_path}\n\n")
        f.write(f"Total metadata entries: {total_csv}\n")
        f.write(f"Total files in folder: {total_folder}\n")
        f.write(f"Matched: {matched_count}\n")
        f.write(f"Missing from folder: {missing_count}\n")
        f.write(f"Extra in folder: {extra_count}\n\n")

        if perfect_match:
            f.write("✅ PERFECT MATCH: All files are consistent between CSV and folder.\n\n")
        else:
            f.write("⚠️ MISMATCH DETECTED:\n")
            if missing_count > 0:
                f.write(f"  - Missing from folder ({missing_count}):\n")
                for item in missing[:10]:
                    f.write(f"    • {item}\n")
                if missing_count > 10:
                    f.write("    ... (truncated)\n")
            if extra_count > 0:
                f.write(f"\n  - Extra in folder ({extra_count}):\n")
                for item in extra[:10]:
                    f.write(f"    • {item}\n")
                if extra_count > 10:
                    f.write("    ... (truncated)\n")
            f.write("\n")

        f.write("📄 Output files:\n")
        f.write(f"  - Matched: {matched_csv}\n")
        f.write(f"  - Missing from folder: {missing_csv}\n")
        f.write(f"  - Extra in folder: {extra_csv}\n")

    print("\n✅ Verification complete.")
    print(f"  Matched: {matched_count}")
    print(f"  Missing: {missing_count}")
    print(f"  Extra: {extra_count}")
    print(f"  Report saved to: {report_txt}")

    if perfect_match:
        print("🎯 Result: PERFECT MATCH between folder and CSV metadata.")
    else:
        print("⚠️ Some mismatches detected. See report for details.")


def main():
    parser = argparse.ArgumentParser(description="Strictly verify folder and metadata CSV consistency.")
    parser.add_argument("--folder", default="C:/Users/svs26/Desktop/images", help="Path to the image folder.")
    parser.add_argument("--csv", default="C:/Users/svs26/Desktop/input.csv", help="Path to the metadata CSV.")
    parser.add_argument("--column", default="Image Path", help="Column name in the CSV with image paths/names.")
    parser.add_argument("--out", default="C:/Users/svs26/Desktop/output", help="Directory to save reports and CSVs.")
    args = parser.parse_args()

    verify_folder_and_metadata(args.csv, args.folder, args.column, args.out)


if __name__ == "__main__":
    main()