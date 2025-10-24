#!/usr/bin/env python3
"""
Ensure that every sample in a LLaVA-OneVision dataset has exactly one "<image>\\n"
token in the first human turn's "value".

Rules:
- If no <image> token is present → prepend "<image>\\n".
- If multiple <image> tokens are present → keep exactly one "<image>\\n" at the start.
- If one <image> token is already present → leave as is.
- Always preserve newline formatting: exactly one "\n" after the token.
- Output a corrected JSON (or JSONL) and a CSV report.
"""

import os
import json
import csv
import argparse
import re

def enforce_single_image_token(input_path, report_path, output_path):
    # Load dataset (supports JSON and JSONL)
    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            is_jsonl = False
        except json.JSONDecodeError:
            f.seek(0)
            data = [json.loads(line) for line in f if line.strip()]
            is_jsonl = True

    corrected_data = []
    report = []

    for sample in data:
        sample_id = sample.get("id", "")
        convs = sample.get("conversations", [])
        modified = False
        issue = ""

        # Locate first human message
        for i, turn in enumerate(convs):
            if turn.get("from") == "human":
                value = turn.get("value", "")
                # Count number of <image> occurrences
                token_count = len(re.findall(r"<image>", value))

                if token_count == 0:
                    # Missing: prepend <image>\n
                    new_value = "<image>\n" + value.lstrip()
                    issue = "No <image> token found → added one"
                    modified = True

                elif token_count > 1:
                    # Too many: remove all and reinsert one
                    clean_text = re.sub(r"\s*<image>\s*", "", value)
                    new_value = "<image>\n" + clean_text.lstrip()
                    issue = f"Multiple <image> tokens ({token_count}) → reduced to one"
                    modified = True

                else:
                    # Exactly one token: ensure format "<image>\n"
                    # Fix if missing proper newline right after
                    if not re.match(r"^<image>\s*\n", value):
                        new_value = re.sub(r"^<image>\s*", "<image>\n", value)
                        issue = "Single <image> token → fixed newline format"
                        modified = True
                    else:
                        new_value = value

                if modified:
                    convs[i]["value"] = new_value
                    report.append({
                        "id": sample_id,
                        "issue": issue,
                        "original_value": value.strip().replace("\n", " ")
                    })
                break
        else:
            # No human message found
            report.append({
                "id": sample_id,
                "issue": "No human turn found",
                "original_value": ""
            })

        corrected_data.append(sample)

    # Write report CSV
    with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["id", "issue", "original_value"])
        writer.writeheader()
        writer.writerows(report)

    # Write corrected dataset
    if is_jsonl:
        with open(output_path, "w", encoding="utf-8") as f:
            for sample in corrected_data:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(corrected_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Processed {len(data)} samples")
    print(f"⚙️  Corrected {len(report)} samples → {report_path}")
    print(f"💾 Cleaned dataset saved as → {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize to exactly one <image> token per first human turn in LLaVA-OneVision dataset.")
    parser.add_argument("--input", default="annotations.json", help="Path to input JSON or JSONL file.")
    parser.add_argument("--report", default="single_image_token_report.csv", help="Path to CSV report file.")
    parser.add_argument("--output", default="annotations_single_image.json", help="Path to corrected JSON/JSONL output file.")
    args = parser.parse_args()

    enforce_single_image_token(args.input, args.report, args.output)