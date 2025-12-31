import os
import json
import pandas as pd

def count_entries_in_csv(file_path):
    df = pd.read_csv(file_path)
    return len(df)

def count_entries_in_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return len(data)

def count_files_in_folder(folder_path):
    return len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])

def compare_entries_and_frames(csv_path, json_path, frame_folder_path, output_file):
    csv_entries = count_entries_in_csv(csv_path) if os.path.exists(csv_path) else 0
    json_entries = count_entries_in_json(json_path) if os.path.exists(json_path) else 0
    frame_files = count_files_in_folder(frame_folder_path) if os.path.exists(frame_folder_path) else 0

    discrepancies = []

    if csv_entries != frame_files:
        discrepancies.append(f"Discrepancy: .csv file has {csv_entries} entries, but frame folder has {frame_files} files.")

    if json_entries != frame_files:
        discrepancies.append(f"Discrepancy: .json file has {json_entries} entries, but frame folder has {frame_files} files.")

    if not discrepancies:
        print(f"No discrepancies found in {frame_folder_path}. The number of entries matches the number of files.")
    else:
        print(f"\nDiscrepancies Summary for {frame_folder_path}:")
        for discrepancy in discrepancies:
            print(discrepancy)

    with open(output_file, 'a') as f:
        f.write(f"Results for {frame_folder_path}:\n")
        f.write(f"Number of entries in .csv file: {csv_entries}\n")
        f.write(f"Number of entries in .json file: {json_entries}\n")
        f.write(f"Number of files in frame folder: {frame_files}\n")
        if not discrepancies:
            f.write("No discrepancies found. The number of entries matches the number of files.\n")
        else:
            f.write("\nDiscrepancies Summary:\n")
            for discrepancy in discrepancies:
                f.write(f"{discrepancy}\n")
        f.write("\n" + "="*50 + "\n")

def check_parent_folders(csv_json_parent_folder, frame_parent_folder, output_file):
    csv_json_subfolders = [os.path.join(csv_json_parent_folder, d) for d in os.listdir(csv_json_parent_folder) if os.path.isdir(os.path.join(csv_json_parent_folder, d))]

    for csv_json_folder in csv_json_subfolders:
        folder_name = os.path.basename(csv_json_folder)
        csv_path = os.path.join(csv_json_folder, f"{folder_name}.csv")
        json_path = os.path.join(csv_json_folder, f"{folder_name}.json")
        frame_folder = os.path.join(frame_parent_folder, folder_name)

        compare_entries_and_frames(csv_path, json_path, frame_folder, output_file)

csv_json_parent_folder = 'C:/Users/s.varela/Desktop/Weekly Findings/W52/annotations/youtube_v3_1fps_v2/'
frame_parent_folder = 'C:/Users/s.varela/Desktop/datasets/test_videos_YT/videos_subsampled_1fps/'
output_file = 'C://Users//s.varela//Desktop//Weekly Findings//2026//W01//Validation_Checking//validation_youtube_v3_1fps_v2.txt'

check_parent_folders(csv_json_parent_folder, frame_parent_folder, output_file)