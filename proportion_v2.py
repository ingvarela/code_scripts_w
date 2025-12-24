import os
import json
from collections import defaultdict
import matplotlib.pyplot as plt


# --------------------
# Config
# --------------------
FILE1 = "suspicious_activity_detection_llava_dataset_test_youtube_v3_0.5fps.json"
FILE2 = "suspicious_activity_detection_llava_dataset_test_youtube_v3_1fps_v2.json"

LABEL1 = "0.5fps"
LABEL2 = "1fps"

OUT_DIR = "output"
PLOT_DIR = os.path.join(OUT_DIR, "plots")
CSV_PATH = os.path.join(OUT_DIR, "per_folder_proportions.csv")

os.makedirs(PLOT_DIR, exist_ok=True)


# --------------------
# Helpers
# --------------------
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_answer(v):
    v = str(v).strip().lower()
    if v == "yes":
        return "yes"
    if v == "no":
        return "no"
    return "other"


def extract_subfolder(image_path):
    parts = image_path.replace("\\", "/").split("/")
    if "videos_subsampled_1fps" in parts:
        return parts[parts.index("videos_subsampled_1fps") + 1]
    if "videos_sampled_1fps" in parts:
        return parts[parts.index("videos_sampled_1fps") + 1]
    return parts[-2]  # fallback


def accumulate(dataset):
    counts = defaultdict(lambda: {"yes": 0, "no": 0, "other": 0, "total": 0})

    for entry in dataset:
        folder = extract_subfolder(entry["image"])
        for c in entry["conversations"]:
            if c["from"] != "gpt":
                continue
            ans = normalize_answer(c["value"])
            counts[folder][ans] += 1
            counts[folder]["total"] += 1

    return counts


def proportions(c):
    if c["total"] == 0:
        return 0, 0, 0
    return (
        c["yes"] / c["total"] * 100,
        c["no"] / c["total"] * 100,
        c["other"] / c["total"] * 100,
    )


# --------------------
# Main
# --------------------
data1 = load_json(FILE1)
data2 = load_json(FILE2)

c1 = accumulate(data1)
c2 = accumulate(data2)

folders = sorted(set(c1.keys()) | set(c2.keys()))

# CSV header
csv_rows = [
    "folder,file,yes_prop,no_prop,other_prop,total_gpt"
]

for folder in folders:
    p1 = proportions(c1.get(folder, {"yes": 0, "no": 0, "other": 0, "total": 0}))
    p2 = proportions(c2.get(folder, {"yes": 0, "no": 0, "other": 0, "total": 0}))

    # CSV rows
    csv_rows.append(f"{folder},{LABEL1},{p1[0]:.4f},{p1[1]:.4f},{p1[2]:.4f},{c1.get(folder, {}).get('total', 0)}")
    csv_rows.append(f"{folder},{LABEL2},{p2[0]:.4f},{p2[1]:.4f},{p2[2]:.4f},{c2.get(folder, {}).get('total', 0)}")

    # Plot
    categories = ["Yes", "No", "Other"]
    x = range(3)
    width = 0.35

    plt.figure()
    plt.bar([i - width/2 for i in x], p1, width, label=LABEL1)
    plt.bar([i + width/2 for i in x], p2, width, label=LABEL2)
    plt.xticks(x, categories)
    plt.ylabel("Proportion (%)")
    plt.title(folder)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, f"{folder}.png"), dpi=150)
    plt.close()

# Write CSV
with open(CSV_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(csv_rows))

print("Done ✅")
print(f"CSV saved to: {CSV_PATH}")
print(f"Plots saved to: {PLOT_DIR}")