import os
import re
import pandas as pd

# === CONFIGURATION ===
images_folder = "/workspace/shared-dir/sample-notebooks/imported-data/s.varela/aisummarization/experimental/stage1_5_gen/SRT_UReader/SRT_ChartQA/images"
datasets_base_path = "/workspace/shared-dir/sample-notebooks/imported-data/s.varela/aisummarization/experimental/stage1_5_gen/SRT_UReader/SRT_ChartQA/datasets"
base_url = "https://github.com/owid/owid-datasets/tree/master/datasets/"
default_license_note = "CC BY 4.0"
output_file = "generated_from_images.csv"


# === FUNCTION DEFINITIONS ===

def extract_prefix(filename):
    """
    Detects which pattern the image belongs to and returns (case_type, prefix).
    case_type can be: 'chartqa', 'img', or 'imgD'.
    """
    if re.search(r"^chartqa_csv_file_\d+", filename):
        match = re.search(r"(chartqa_csv_file_\d+)", filename)
        if match:
            return "chartqa", match.group(1)

    elif re.search(r"^img\d+", filename):
        match = re.search(r"(img\d+)", filename)
        if match:
            return "img", match.group(1)

    elif re.search(r"^imgD_", filename):
        match = re.search(r"(imgD_\w+)", filename)
        if match:
            return "imgD", match.group(1)

    return None, None


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

image_files = [
    f for f in os.listdir(images_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"))
]

records = []

for img in image_files:
    image_path = os.path.join(images_folder, img)
    case_type, prefix = extract_prefix(img)

    # --- Case 1: ChartQA datasets ---
    if case_type == "chartqa":
        github_url = get_github_path_from_prefix(prefix)
        license_note = default_license_note

    # --- Case 2: Our World in Data images (img#) ---
    elif case_type == "img":
        github_url = ""
        license_note = "CC BY 4.0 Our World In Data"
        print(f"🌍 OWID image detected: {img}")

    # --- Case 3: OECD.org images (imgD_) ---
    elif case_type == "imgD":
        github_url = ""
        license_note = "CC BY 4.0 OECD.org"
        print(f"🏛️ OECD image detected: {img}")

    # --- Case 4: Unrecognized pattern ---
    else:
        print(f"⚠️ No valid prefix found in: {img}")
        continue

    records.append({
        "Image Path": image_path,
        "CSV Path": github_url,
        "License Note": license_note
    })

# === SAVE RESULTS ===
df = pd.DataFrame(records)
df.to_csv(output_file, index=False)

print(f"\n✅ Generated CSV successfully → {output_file}")