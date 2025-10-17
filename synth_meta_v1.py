import pandas as pd
import os
import argparse

def generate_metadata(input_csv, output_csv=None):
    # Read the input CSV
    df = pd.read_csv(input_csv)

    # Map the columns to the new format
    output_df = pd.DataFrame({
        "Image Path": df["Id"],
        "Image Source": df["background_src"],
        "License Image Source": "CC BY S.A. 4.0",
        "Text": df["text_source"],
        "License Text Source": "Public Domain: Gutenberg Project"
    })

    # If no output path specified, create one next to input
    if not output_csv:
        base_dir = os.path.dirname(input_csv)
        output_csv = os.path.join(base_dir, "metadata_generated.csv")

    # Save to CSV
    output_df.to_csv(output_csv, index=False)
    print(f"✅ Metadata generated and saved to: {output_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate metadata CSV from existing data.")
    parser.add_argument("--input_csv", required=True, help="Path to the source CSV file.")
    parser.add_argument("--output_csv", required=False, help="Optional output CSV file path.")
    args = parser.parse_args()

    generate_metadata(args.input_csv, args.output_csv)
