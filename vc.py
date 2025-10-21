#!/usr/bin/env python3
"""
Fast Image Folder Comparison (Edge-Based Hash Matching)
-------------------------------------------------------
Compares images between two folders, focusing on the sides/top/bottom regions.
Produces a CSV mapping: Image Path | Image Source | License Image ("CC BY 4.0").
Optimized for large datasets (30K+ images).
"""

import os
import csv
import imagehash
from PIL import Image
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

# ======== CONFIG ========
HASH_FUNC = imagehash.phash  # perceptual hash (robust)
EDGE_RATIO = 0.15            # fraction of image height/width used from edges
HASH_SIZE = 16               # higher = more detail
DIST_THRESHOLD = 6           # smaller = stricter match
# =========================


def compute_edge_hash(image_path):
    """Compute hash for the image using only edge regions."""
    try:
        img = Image.open(image_path).convert("L")
        w, h = img.size
        dw, dh = int(w * EDGE_RATIO), int(h * EDGE_RATIO)

        # extract borders (top, bottom, left, right)
        edges = [
            img.crop((0, 0, w, dh)),           # top
            img.crop((0, h - dh, w, h)),       # bottom
            img.crop((0, 0, dw, h)),           # left
            img.crop((w - dw, 0, w, h))        # right
        ]

        # combine edges into one strip for hashing
        combined = Image.new("L", (w, dh * 4))
        for i, edge in enumerate(edges):
            combined.paste(edge, (0, i * dh))

        return image_path, HASH_FUNC(combined, hash_size=HASH_SIZE)
    except Exception:
        return image_path, None


def parallel_hash(folder):
    """Compute hashes for all images in a folder (parallelized)."""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]

    with Pool(cpu_count()) as p:
        hashes = list(tqdm(p.imap(compute_edge_hash, files), total=len(files), desc=f"Hashing {folder}"))
    return {path: h for path, h in hashes if h is not None}


def match_folders(folder_a, folder_b, output_csv="image_matches.csv"):
    """Compare edge hashes of two folders and save results."""
    print("Computing hashes for Folder A (base images)...")
    hashes_a = parallel_hash(folder_a)

    print("Computing hashes for Folder B (comparison images)...")
    hashes_b = parallel_hash(folder_b)

    results = []
    b_items = list(hashes_b.items())

    print("Matching images...")
    for path_a, hash_a in tqdm(hashes_a.items(), total=len(hashes_a)):
        best_match = None
        best_dist = float("inf")

        for path_b, hash_b in b_items:
            dist = hash_a - hash_b
            if dist < best_dist:
                best_match = path_b
                best_dist = dist

        if best_dist <= DIST_THRESHOLD:
            results.append([path_a, best_match, "CC BY 4.0"])

    print(f"Saving {len(results)} matches to {output_csv}")
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Image Path", "Image Source", "License Image"])
        writer.writerows(results)

    print("✅ Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare two folders of images using edge-based hashing.")
    parser.add_argument("--folder_a", required=True, help="Path to first folder (base images).")
    parser.add_argument("--folder_b", required=True, help="Path to second folder (comparison images).")
    parser.add_argument("--output_csv", default="image_matches.csv", help="Output CSV filename.")
    args = parser.parse_args()

    match_folders(args.folder_a, args.folder_b, args.output_csv)
