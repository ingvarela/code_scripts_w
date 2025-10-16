import pandas as pd
import os

# Read the main CSV file
df = pd.read_csv('my csv file.csv')

# Base GitHub path for OWID datasets
base_url = "https://github.com/owid/owid-datasets/tree/master/datasets/"

# Function to construct the full GitHub link
def get_github_path(local_path):
    # Clean and normalize the path
    local_path = str(local_path).strip().strip('"').strip("'")
    local_path = os.path.normpath(local_path)

    # Get the parent directory where metadata might be
    parent_dir = os.path.dirname(local_path)

    # Possible metadata filenames
    candidates = [
        os.path.join(parent_dir, "metadata.csv"),
        os.path.join(parent_dir, "renaming_metadata.csv")
    ]

    # Find the first one that exists
    metadata_path = None
    for candidate in candidates:
        print(f"🔍 Checking: {candidate}")
        if os.path.exists(candidate):
            metadata_path = candidate
            print(f"✅ Found metadata file: {candidate}")
            break

    if metadata_path is None:
        print(f"❌ No metadata file found for: {local_path}\n")
        return None

    # Try to read metadata
    try:
        metadata = pd.read_csv(metadata_path)
    except Exception as e:
        print(f"❌ Error reading {metadata_path}: {e}")
        return None

    # Extract required columns safely
    try:
        folder_name = str(metadata.loc[0, "Original Folder Name"]).strip()
        csv_name = str(metadata.loc[0, "Original CSV Name"]).strip()
    except KeyError:
        print(f"❌ Missing expected columns in {metadata_path}")
        return None

    # Build and return the full GitHub URL
    github_url = f"{base_url}{folder_name}/{csv_name}"
    print(f"🌐 Generated URL: {github_url}\n")
    return github_url

# Apply the function to every path in your CSV Path column
df['CSV Path'] = df['CSV Path'].apply(get_github_path)

# Save the updated DataFrame to a new CSV file
output_file = 'updated my csv file.csv'
df.to_csv(output_file, index=False)

print(f"✅ CSV file updated successfully → {output_file}")
