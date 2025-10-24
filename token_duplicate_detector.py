#!/usr/bin/env python3
"""
Count <image> tokens in the first human turn of each sample in a LLaVA-OneVision dataset.
If more than one <image> token is found, log that sample in a CSV report.

Default input: annotations.json
Output: multiple_image_token_report.csv
"""

import json
import csv
import argparse
import re

def count_image_tokens(input_path, report_path):
    # Load dataset (supports JSON and JSONL)
    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            f.seek(0)
            data = [json.loads(line) for line in f if line.strip()]

    report = []
    total_samples = len(data)
    multi_token_count = 0

    for sample in data:
        sample_id = sample.get("id", "")
        convs = sample.get("conversations", [])

        # Find first human message
        first_human_value = None
        for turn in convs:
            if turn.get("from") == "human":
                first_human_value = turn.get("value", "")
                break

        if first_human_value is None:
            continue

        # Count <image> occurrences
        token_count = len(re.findall(r"<image>", first_human_value))

        if token_count > 1:
            multi_token_count += 1
            report.append({
                "id": sample_id,
                "image_token_count": token_count,
                "first_human_value": first_human_value.strip().replace("\n", " ")
            })

    # Save CSV report
    with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["id", "image_token_count", "first_human_value"])
        writer.writeheader()
        writer.writerows(report)

    print(f"✅ Total samples checked: {total_samples}")
    print(f"⚠️ Samples with >1 <image> token: {multi_token_count}")
    print(f"💾 Report saved to: {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count <image> tokens per sample (first human turn only).")
    parser.add_argument("--input", default="annotations.json", help="Path to input JSON or JSONL file.")
    parser.add_argument("--report", default="multiple_image_token_report.csv", help="Path to output CSV report.")
    args = parser.parse_args()

    count_image_tokens(args.input, args.report)