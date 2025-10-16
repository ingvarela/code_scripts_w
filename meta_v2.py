import pandas as pd
import os

# Base GitHub path for OWID datasets
base_url = "https://github.com/owid/owid-datasets/tree/master/datasets/"

# Path where your original CSV files are stored
input_folder = "path/to/your/folder"
output_folder = os.path.join(input_folder, "updated_csvs")

# Ensure output folder exists
os.makedirs(output_folder, exist_ok=True)


def get_github_path(local_path):
    """Reads metadata.csv from the given local path and builds full GitHub URL."""
    metadata_path = os.path.join(local_path, "metadata.csv")

    if not os.path.exists(metadata_path):
        print(f"⚠️ metadata.csv not found in {local_path}")
        return None

    try:
        metadata = pd.read_csv(metadata_path)
    except Exception as e:
        print(f"❌ Error reading {metadata_path}: {e}")
        return None

    try:
        folder_name = str(metadata.loc[0, "Original Folder Name"]).strip()
        csv_name = str(metadata.loc[0, "Original CSV Name"]).strip()
    except KeyError:
        print(f"❌ Missing expected columns in {metadata_path}")
        return None

    return f"{base_url}{folder_name}/{csv_name}"


# Iterate through all CSV files in the input folder
for file_name in os.listdir(input_folder):
    if file_name.endswith(".csv"):
        input_csv = os.path.join(input_folder, file_name)
        print(f"🔍 Processing {input_csv}...")

        try:
            df = pd.read_csv(input_csv)
        except Exception as e:
            print(f"❌ Failed to read {file_name}: {e}")
            continue

        if 'CSV Path' not in df.columns:
            print(f"⚠️ Skipping {file_name}: no 'CSV Path' column found.")
            continue

        # Generate GitHub URLs for each row
        df['GitHub Path'] = df['CSV Path'].apply(get_github_path)

        # Save updated CSV file
        output_csv = os.path.join(output_folder, f"updated_{file_name}")
        df.to_csv(output_csv, index=False)
        print(f"✅ Saved updated file → {output_csv}\n")

print("🎉 All CSV files processed successfully.")
