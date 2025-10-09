import os
import csv
import re

def generate_metadata(folder_path):
    output_csv = 'gutenberg_book_page.csv'
    header = ['Image Location in Folder', 'Gutenberg Book ID', 'Page', 'URL to the image', 'License Note']
    rows = []

    # Regex pattern to match .<book_id>_page<page>.png
    pattern = re.compile(r'\.(\d+)_page(\d+)\.png$', re.IGNORECASE)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.png'):
            match = pattern.match(filename)
            if match:
                book_id = match.group(1)
                page = match.group(2)
                image_path = os.path.join(folder_path, filename)
                url = f"https://www.gutenberg.org/files/{book_id}/{book_id}-pdf.pdf#page={page}"
                license_note = "Public domain. Source: Project Gutenberg."
                rows.append([image_path, book_id, page, url, license_note])
            else:
                print(f"Skipping file (invalid format): {filename}")

    # Write metadata to CSV
    with open(output_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Metadata CSV generated: {output_csv}")

# Example usage:
# generate_metadata('/path/to/your/image/folder')
