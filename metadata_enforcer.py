import os
import pandas as pd

def join_csv_files(folder_path, output_filename="joined.csv"):
    # Ensure folder exists
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"The folder '{folder_path}' does not exist.")
    
    csv_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".csv")]
    if not csv_files:
        raise FileNotFoundError("No CSV files found in the provided folder.")

    combined_df = None
    first = True

    for file in csv_files:
        file_path = os.path.join(folder_path, file)
        print(f"Processing: {file_path}")
        if first:
            # Read first file normally
            combined_df = pd.read_csv(file_path, encoding="utf-8-sig")
            first = False
        else:
            # Read rest skipping header, same column count enforced
            df = pd.read_csv(file_path, header=None, skiprows=1, encoding="utf-8-sig")
            
            # Force same number of columns starting from column A
            df = df.iloc[:, :len(combined_df.columns)]
            df.columns = combined_df.columns
            
            combined_df = pd.concat([combined_df, df], ignore_index=True)
    
    output_path = os.path.join(folder_path, output_filename)
    combined_df.to_csv(output_path, index=False)
    print(f"✅ Combined {len(csv_files)} CSV files into: {output_path}")

# Example usage:
# join_csv_files("C:/Users/you/Desktop/my_csvs")
