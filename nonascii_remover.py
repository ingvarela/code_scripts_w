import json
import os
import argparse

def remove_non_ascii(text):
    """Remove all non-ASCII characters from a string."""
    return ''.join(ch for ch in text if ord(ch) < 128)

def main():
    parser = argparse.ArgumentParser(description="Remove non-ASCII chars from 'value' fields in all_metadata.json")
    parser.add_argument("--input", required=True, help="Path to all_metadata.json")
    parser.add_argument("--output", help="Path to save cleaned JSON (default: overwrite input)")
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output if args.output else input_path

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed_count = 0
    for record in data:
        if "conversations" in record:
            for conv in record["conversations"]:
                if "value" in conv and isinstance(conv["value"], str):
                    cleaned = remove_non_ascii(conv["value"])
                    if cleaned != conv["value"]:
                        conv["value"] = cleaned
                        changed_count += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Cleaned {changed_count} entries. Saved to: {output_path}")

if __name__ == "__main__":
    main()