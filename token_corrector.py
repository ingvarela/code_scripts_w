#!/usr/bin/env python3
"""
Check each LLaVA-OneVision annotation to ensure the first human turn starts
with "<image>\\n". If missing, log it in a CSV report and create a corrected
JSON file with the token added (original file is untouched).

Default input: annotations.json
Outputs:
- missing_image_token_report.csv
- annotations_corrected.json
"""

import os
import json
import csv
import argparse

def check_and_fix_first_human_token(input_path, report_path, corrected_path):
    # Load dataset (handle JSON or JSONL)
    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            is_jsonl = False
        except json.JSONDecodeError:
            # Handle JSONL (line-based)
            f.seek(0)
            data = [json.loads(line) for line in f if line.strip()]
            is_jsonl = True

    report = []
    corrected_data = []

    for sample in data:
        sample_id = sample.get("id", "")
        convs = sample.get("conversations", [])

        # Find the first human turn
        for i, turn in enumerate(convs):
            if turn.get("from") == "human":
                value = turn.get("value", "")
                if not value.startswith("<image>\n"):
                    report.append({
                        "id": sample_id,
                        "issue": "Missing or malformed <image>\\n token",
                        "original_value": value.strip().replace("\n", " ")
                    })
                    # Fix it
                    convs[i]["value"] = "<image>\n" + value.lstrip()
                break  # only check first human turn
        else:
            # No human turn found
            report.append({
                "id": sample_id,
                "issue": "No human turn found",
                "original_value": ""
            })

        corrected_data.append(sample)

    # Save CSV report
    with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["id", "issue", "original_value"])
        writer.writeheader()
        writer.writerows(report)

    # Save corrected dataset
    if is_jsonl:
        with open(corrected_path, "w", encoding="utf-8") as f:
            for sample in corrected_data:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    else:
        with open(corrected_path, "w", encoding="utf-8") as f:
            json.dump(corrected_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Checked {len(data)} samples")
    print(f"⚠️ {len(report)} issues found → {report_path}")
    print(f"💾 Corrected dataset saved as → {corrected_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check and fix missing <image>\\n token in first human turn.")
    parser.add_argument("--input", default="annotations.json", help="Input JSON or JSONL file.")
    parser.add_argument("--report", default="missing_image_token_report.csv", help="Path for CSV report.")
    parser.add_argument("--output", default="annotations_corrected.json", help="Path for corrected JSON output.")
    args = parser.parse_args()

    check_and_fix_first_human_token(args.input, args.report, args.output)