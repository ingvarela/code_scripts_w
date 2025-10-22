import os
import pandas as pd

# === CONFIGURATION ===
# Folder containing your images
images_folder = "/workspace/shared-dir/sample-notebooks/imported-data/s.varela/aisummarization/experimental/stage1_5_gen/SRT_UReader/SRT_ChartQA/images"

# Base path where your datasets and metadata files exist
datasets_base_path = "/workspace/shared-dir/sample-notebooks/imported-data/s.varela/aisummarization/experimental/stage1_5_gen/SRT_UReader/SRT_ChartQA/datasets"

# Base GitHub path
base_url = "https://github.com/owid/owid-datasets/tree/master/datasets/"

# Default license note
license_note = "CC BY 4.0"

# Output CSV filename
output_file = "generated_from_images.csv"


# === FUNCTION DEFINITIONS ===

def get_dataset_prefix(filename):
    """Extract dataset prefix from image filename (before first underscore)."""
    return filename.split("_")[0]


def get_github_path_from_prefix(prefix):
    """Locate metadata for a given dataset prefix and build full GitHub URL."""
    dataset_folder = os.path.join(datasets_base_path, prefix)

    # Possible metadata files
    candidates = [
        os.path.join(dataset_folder, "metadata.csv"),
        os.path.join(dataset_folder, "renaming_metadata.csv")
    ]

    metadata_path = None
    for candidate in candidates:
        print(f"🔍 Checking: {candidate}")
        if os.path.exists(candidate):
            metadata_path = candidate
            print(f"✅ Found metadata file: {candidate}")
            break

    if metadata_path is None:
        print(f"❌ No metadata found for prefix: {prefix}")
        return None

    # Read metadata
    try:
        metadata = pd.read_csv(metadata_path)
    except Exception as e:
        print(f"❌ Error reading {metadata_path}: {e}")
        return None

    # Extract fields
    try:
        folder_name = str(metadata.loc[0, "Original Folder Name"]).strip()
        csv_name = str(metadata.loc[0, "Original CSV Name"]).strip()
    except KeyError:
        print(f"❌ Missing expected columns in {metadata_path}")
        return None

    github_url = f"{base_url}{folder_name}/{csv_name}"
    print(f"🌐 Generated URL for {prefix}: {github_url}\n")
    return github_url


# === MAIN SCRIPT LOGIC ===

# Collect all images
image_files = [
    f for f in os.listdir(images_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"))
]

# Prepare rows for the final DataFrame
records = []

for img in image_files:
    image_path = os.path.join(images_folder, img)
    prefix = get_dataset_prefix(img)
    github_url = get_github_path_from_prefix(prefix)
    records.append({
        "Image Path": image_path,
        "CSV Path": github_url,
        "License Note": license_note
    })

# Create the DataFrame and save
df = pd.DataFrame(records)
df.to_csv(output_file, index=False)

print(f"\n✅ Generated CSV successfully → {output_file}")