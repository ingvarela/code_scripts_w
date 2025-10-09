import os
import pandas as pd

def join_csv_files(folder_path, output_filename="joined.csv"):
    # Ensure folder exists
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"The folder '{folder_path}' does not exist.")
    
    # Find all CSV files
    csv_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".csv")]
    if not csv_files:
        raise FileNotFoundError("No CSV files found in the provided folder.")

    combined_df = pd.DataFrame()
    first = True

    for file in csv_files:
        file_path = os.path.join(folder_path, file)
        if first:
            # Read first file including header
            df = pd.read_csv(file_path)
            first = False
        else:
            # Read subsequent files skipping header
            df = pd.read_csv(file_path, header=None, skiprows=1)
        combined_df = pd.concat([combined_df, df], ignore_index=True)

    # Save combined CSV
    output_path = os.path.join(folder_path, output_filename)
    combined_df.to_csv(output_path, index=False)
    print(f"✅ Combined {len(csv_files)} CSV files into: {output_path}")

# Example usage:
# join_csv_files("C:/Users/yourname/Desktop/my_csv_folder")
