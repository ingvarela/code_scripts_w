import pandas as pd
import os

# Read the main CSV file
df = pd.read_csv('my csv file.csv')

# Base GitHub path for OWID datasets
base_url = "https://github.com/owid/owid-datasets/tree/master/datasets/"

# Function to construct the full GitHub link
def get_github_path(local_path):
    metadata_path = os.path.join(local_path, "metadata.csv")

    # Check if metadata.csv exists
    if not os.path.exists(metadata_path):
        print(f"⚠️ metadata.csv not found in {local_path}")
        return None

    # Read the metadata file
    try:
        metadata = pd.read_csv(metadata_path)
    except Exception as e:
        print(f"❌ Error reading {metadata_path}: {e}")
        return None

    # Extract folder and file names
    try:
        folder_name = str(metadata.loc[0, "Original Folder Name"]).strip()
        csv_name = str(metadata.loc[0, "Original CSV Name"]).strip()
    except KeyError:
        print(f"❌ Missing expected columns in {metadata_path}")
        return None

    # Build full GitHub URL
    return f"{base_url}{folder_name}/{csv_name}"

# Apply the function to every path in your CSV Path column
df['CSV Path'] = df['CSV Path'].apply(get_github_path)

# Save the updated DataFrame to a new CSV file
df.to_csv('updated my csv file.csv', index=False)

print("✅ CSV file updated successfully.")
