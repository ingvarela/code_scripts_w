"""
Generate an attribution file for reused charts from OWID and OECD.

- Handles two main subsets:
  1. Our World in Data (CC BY 4.0)
  2. OECD (CC BY 4.0, with restrictions)

- Specifies that images are reused verbatim (unmodified).
- Produces ATTRIBUTIONS.txt and ATTRIBUTIONS.json
"""

import os
import json
from datetime import date

# Example chart records (replace with your actual list)
charts = [
    {
        "title": "Global CO₂ Emissions",
        "source": "Our World in Data",
        "url": "https://ourworldindata.org/co2-and-other-greenhouse-gas-emissions",
        "license": "CC BY 4.0",
        "usage": "Verbatim reuse (no modifications).",
        "notes": "Our World in Data (Global Change Data Lab)."
    },
    {
        "title": "Education Spending by Country",
        "source": "OECD",
        "url": "https://data.oecd.org/eduresource/public-spending-on-education.htm",
        "license": "CC BY 4.0",
        "usage": "Verbatim reuse (no modifications).",
        "notes": "OECD, charts may not imply endorsement; logos/branding excluded."
    }
]

# === Output TXT ===
txt_lines = []
txt_lines.append("ATTRIBUTION FILE")
txt_lines.append(f"Generated on {date.today().isoformat()}")
txt_lines.append("="*60)
txt_lines.append("")

for ch in charts:
    txt_lines.append(f"Title   : {ch['title']}")
    txt_lines.append(f"Source  : {ch['source']}")
    txt_lines.append(f"URL     : {ch['url']}")
    txt_lines.append(f"License : {ch['license']}")
    txt_lines.append(f"Usage   : {ch['usage']}")
    txt_lines.append(f"Notes   : {ch['notes']}")
    txt_lines.append("-"*60)

with open("ATTRIBUTIONS.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(txt_lines))

print("ATTRIBUTIONS.txt created.")

# === Optional: Output JSON ===
with open("ATTRIBUTIONS.json", "w", encoding="utf-8") as f:
    json.dump(charts, f, indent=2, ensure_ascii=False)

print("ATTRIBUTIONS.json created.")
