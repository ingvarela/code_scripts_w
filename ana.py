#!/usr/bin/env python3
"""
Compare numbers extracted from two CSV files with encoding fallback support.
"""

import csv
import os
import re
import argparse
from collections import Counter

def open_with_fallback(path):
    """Try UTF-8 first, then Latin-1 if decoding fails."""
    try:
        return open(path, newline='', encoding='utf-8')
    except UnicodeDecodeError:
        print(f"⚠️  Warning: '{path}' not UTF-8 encoded, using Latin-1 fallback.")
        return open(path, newline='', encoding='latin-1')

def extract_number_from_link(link):
    if not link:
        return None
    match = re.search(r'-([0-9]+)(?:$|[^0-9]*)', str(link).strip())
    return match.group(1) if match else None

def extract_number_from_path(path):
    if not path:
        return None
    filename = os.path.basename(str(path).strip())
    match = re.search(r'-([0-9]+)\.(?:jpg|png)$', filename, re.IGNORECASE)
    return match.group(1) if match else None

def compare_csvs(csv_a, column_a, csv_b, column_b, output_csv, matched_csv, not_found_csv):
    with open_with_fallback(csv_a) as f1, \
         open_with_fallback(csv_b) as f2, \
         open(output_csv, 'w', newline='', encoding='utf-8') as fout, \
         open(matched_csv, 'w', newline='', encoding='utf-8') as fmatch, \
         open(not_found_csv, 'w', newline='', encoding='utf-8') as freport:

        reader_a = csv.DictReader(f1)
        reader_b = csv.DictReader(f2)
        writer_all = csv.writer(fout)
        writer_match = csv.writer(fmatch)
        writer_notfound = csv.writer(freport)

        writer_all.writerow(["Link", "Extracted_Num_A", "Image_Path", "Extracted_Num_B", "Match"])
        writer_match.writerow(["Image Path", "Source", "License Note"])
        writer_notfound.writerow(["Type", "Side", "Original_Value", "Extracted_Num"])

        license_note = "Public Domain. Free to use, no attribution needed. https://www.pexels.com/license"

        # Build map from image CSV
        b_map = {}
        for row in reader_b:
            path = row.get(column_b)
            num_b = extract_number_from_path(path)
            if num_b:
                b_map.setdefault(num_b, []).append(path)

        match_count = 0
        no_match_count = 0
        duplicates = []
        unmatched_links = []
        unmatched_paths = set(b_map.keys())

        for row in reader_a:
            link = row.get(column_a)
            num_a = extract_number_from_link(link)
            if not num_a:
                continue

            match_paths = b_map.get(num_a)
            if match_paths:
                match_count += 1
                writer_all.writerow([link, num_a, match_paths[0], num_a, "MATCH"])
                writer_match.writerow([match_paths[0], link, license_note])
                unmatched_paths.discard(num_a)
                if len(match_paths) > 1:
                    duplicates.append(num_a)
            else:
                no_match_count += 1
                writer_all.writerow([link, num_a, "", "", "NO_MATCH"])
                unmatched_links.append((link, num_a))

        # Not-found report
        for link, num in unmatched_links:
            writer_notfound.writerow(["Missing Match", "From Link CSV", link or "N/A", num or "N/A"])
        for num in unmatched_paths:
            for p in b_map[num]:
                writer_notfound.writerow(["Missing Match", "From Image CSV", p or "N/A", num or "N/A"])

        duplicate_count = sum(Counter(duplicates).values())

    print("\n✅ Comparison completed successfully.")
    print(f"   • Full results: {output_csv}")
    print(f"   • Matches only: {matched_csv}")
    print(f"   • Not-found report: {not_found_csv}")
    print(f"\n📊 Summary:")
    print(f"   - Matches found: {match_count}")
    print(f"   - No matches: {no_match_count}")
    print(f"   - Duplicate image IDs: {duplicate_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare numbers from two CSVs with encoding fallback.")
    parser.add_argument("--csv_a", required=True, help="Path to first CSV (with links)")
    parser.add_argument("--column_a", required=True, help="Column name in first CSV")
    parser.add_argument("--csv_b", required=True, help="Path to second CSV (with image paths)")
    parser.add_argument("--column_b", required=True, help="Column name in second CSV")
    parser.add_argument("--output", default="comparison_results.csv", help="Detailed output CSV")
    parser.add_argument("--matched", default="matched_results.csv", help="Simplified matched output CSV")
    parser.add_argument("--notfound", default="not_found_report.csv", help="Unmatched paths/links report CSV")

    args = parser.parse_args()
    compare_csvs(args.csv_a, args.column_a, args.csv_b, args.column_b, args.output, args.matched, args.notfound)