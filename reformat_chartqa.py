import re

json_file = 'data.json'

with open(json_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Only replace paths in the form of image": "..."
updated_content = re.sub(
    r'("image"\s*:\s*")([^"]*?)\bimg\b(\/[^"]*?\.png")',
    lambda m: f'{m.group(1)}{m.group(2)}img01{m.group(3)}',
    content
)

with open(json_file, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print(f"Updated image paths in-place in {json_file} without reformatting.")
