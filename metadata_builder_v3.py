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

    # Get the parent directory where metadata.csv should be
    parent_dir = os.path.dirname(local_path)
    metadata_path = os.path.join(parent_dir, "metadata.csv")

    # Debug print to verify the path being checked
    print(f"🔍 Checking: {metadata_path}")

    # Verify existence
    if not os.path.exists(metadata_path):
        print(f"❌ metadata.csv not found for: {local_path}")
        return None
    else:
        print(f"✅ Found metadata.csv for: {local_path}")

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
