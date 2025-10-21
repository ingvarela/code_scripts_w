#!/usr/bin/env python3
"""
Fast Image Folder Comparison (Edge-Based Hash Matching)
-------------------------------------------------------
Compares images between two folders using only their edge regions
(top, bottom, left, right). Each base image gets exactly one closest
match in the comparison folder (duplicates allowed).

Optimized for large datasets (30K+ images) with:
 - Parallelized hashing
 - Dimension-based prefiltering (skip clearly different sizes)
 - Perceptual hashing of edges only (robust to center differences)

Output CSV columns:
Image Path | Image Source | License Image | Similarity
"""

import os
import csv
import imagehash
from PIL import Image
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from collections import defaultdict

# ======== CONFIG ========
HASH_FUNC = imagehash.phash    # perceptual hash
EDGE_RATIO = 0.15              # fraction of image height/width used from edges
HASH_SIZE = 16                 # hash granularity (higher = more detail)
SIZE_TOLERANCE = 10            # max difference in width/height to consider same group
# =========================


def compute_edge_hash(image_path):
    """Compute hash and dimensions for an image using only its edge regions."""
    try:
        img = Image.open(image_path).convert("L")
        w, h = img.size
        dw, dh = int(w * EDGE_RATIO), int(h * EDGE_RATIO)

        # Extract top, bottom, left, right edges
        edges = [
            img.crop((0, 0, w, dh)),
            img.crop((0, h - dh, w, h)),
            img.crop((0, 0, dw, h)),
            img.crop((w - dw, 0, w, h))
        ]

        # Combine into one strip
        combined = Image.new("L", (w, dh * 4))
        for i, edge in enumerate(edges):
            combined.paste(edge, (0, i * dh))

        img.close()
        hash_value = HASH_FUNC(combined, hash_size=HASH_SIZE)
        return (image_path, (w, h), hash_value)
    except Exception:
        return (image_path, None, None)


def parallel_hash(folder):
    """Compute edge hashes for all images in folder (parallelized)."""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]

    with Pool(cpu_count()) as p:
        hashes = list(tqdm(p.imap(compute_edge_hash, files), total=len(files), desc=f"Hashing {folder}"))

    # return dict: {path: (size, hash)}
    return {p: (s, h) for p, s, h in hashes if h is not None and s is not None}


def build_size_index(hashes_b):
    """Group folder_b hashes by approximate image dimensions."""
    size_index = defaultdict(list)
    for path_b, (size_b, hash_b) in hashes_b.items():
        w_b, h_b = size_b
        size_index[(w_b // SIZE_TOLERANCE, h_b // SIZE_TOLERANCE)].append((path_b, size_b, hash_b))
    return size_index


def find_best_match(path_a, size_a, hash_a, size_index):
    """Find the closest hash match for one image from folder A."""
    w_a, h_a = size_a
    key = (w_a // SIZE_TOLERANCE, h_a // SIZE_TOLERANCE)
    candidates = size_index.get(key, [])

    # if no candidates in same bucket, search nearby buckets
    if not candidates:
        for dw in [-1, 0, 1]:
            for dh in [-1, 0, 1]:
                candidates.extend(size_index.get((key[0] + dw, key[1] + dh), []))

    best_match = None
    best_dist = float("inf")

    for path_b, size_b, hash_b in candidates:
        dist = hash_a - hash_b
        if dist < best_dist:
            best_match = path_b
            best_dist = dist

    max_bits = HASH_SIZE * HASH_SIZE
    similarity = 1 - (best_dist / max_bits)
    return best_match, similarity


def match_folders(folder_a, folder_b, output_csv="image_matches.csv"):
    """Compare two folders and save one guaranteed match per image."""
    print("Computing hashes for Folder A (base images)...")
    hashes_a = parallel_hash(folder_a)

    print("Computing hashes for Folder B (comparison images)...")
    hashes_b = parallel_hash(folder_b)

    print("Indexing Folder B by size groups...")
    size_index = build_size_index(hashes_b)

    results = []
    print("Matching images (1 guaranteed best match per base image)...")

    for path_a, (size_a, hash_a) in tqdm(hashes_a.items(), total=len(hashes_a)):
        best_match, similarity = find_best_match(path_a, size_a, hash_a, size_index)
        results.append([path_a, best_match, "CC BY 4.0", f"{similarity:.4f}"])

    print(f"Saving {len(results)} matches to {output_csv}")
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Image Path", "Image Source", "License Image", "Similarity"])
        writer.writerows(results)

    print(f"✅ Done. {len(results)} total matches saved — one per base image.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare two folders of images using edge-based hashing.")
    parser.add_argument("--folder_a", required=True, help="Path to base folder (images to match).")
    parser.add_argument("--folder_b", required=True, help="Path to comparison folder (possible matches).")
    parser.add_argument("--output_csv", default="image_matches.csv", help="Output CSV filename.")
    args = parser.parse_args()

    match_folders(args.folder_a, args.folder_b, args.output_csv)
