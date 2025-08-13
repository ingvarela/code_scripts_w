import os
import shutil
import pandas as pd
from collections import defaultdict

def _norm(name):  # basename + trim + lowercase
    return os.path.basename(str(name)).strip().lower()

def copy_and_filter_maximize_1to1(
    source_folder,
    destination_folder,
    original_csv_path,
    output_csv_path,
    filename_column="filename",
    write_skip_report=True,
    skip_report_path=None,
):
    os.makedirs(destination_folder, exist_ok=True)

    # ---- Scan source for *base.png (track duplicates by basename) ----
    src_map = defaultdict(list)  # norm_name -> [full_paths...]
    total_candidates = 0
    for root, _, files in os.walk(source_folder):
        for f in files:
            if f.lower().endswith("base.png"):
                total_candidates += 1
                src_map[_norm(f)].append(os.path.join(root, f))

    # ---- Load CSV and compute row counts + single-row index ----
    df = pd.read_csv(original_csv_path)
    if filename_column not in df.columns:
        raise KeyError(f"CSV missing '{filename_column}'. Available: {list(df.columns)}")

    counts = defaultdict(int)
    idxs = defaultdict(list)
    for i, v in df[filename_column].astype(str).items():
        n = _norm(v)
        counts[n] += 1
        idxs[n].append(i)

    # ---- Build skip list + candidates (unique in source AND exactly one row in CSV) ----
    skips = []
    candidates = []
    for name, paths in src_map.items():
        if len(paths) != 1:
            skips.append({"filename": name, "phase": "source_scan",
                          "reason": f"duplicate basename in source ({len(paths)} occurrences)",
                          "details": " | ".join(paths)})
            continue
        c = counts.get(name, 0)
        if c == 0:
            skips.append({"filename": name, "phase": "csv_match", "reason": "missing in CSV (0 rows)", "details": ""})
        elif c > 1:
            skips.append({"filename": name, "phase": "csv_match", "reason": f"multiple rows in CSV ({c} rows)", "details": ""})
        else:
            candidates.append(name)

    # ---- Copy with fault tolerance; record successful names only ----
    copied = []
    for name in sorted(candidates):
        src = src_map[name][0]
        dst = os.path.join(destination_folder, os.path.basename(src))
        try:
            shutil.copy2(src, dst)
            copied.append(name)
        except Exception as e:
            skips.append({"filename": name, "phase": "copy", "reason": "copy_failed", "details": f"{type(e).__name__}: {e}"})

    # ---- Build filtered CSV (exactly one row per successfully copied file) ----
    kept_rows = [idxs[name][0] for name in copied]  # each has exactly one row
    filtered = df.loc[kept_rows].copy()

    # 1:1 parity check (defensive)
    if len(filtered) != len(copied):
        raise RuntimeError(f"Parity error: rows({len(filtered)}) != images({len(copied)})")

    filtered.to_csv(output_csv_path, index=False)

    # ---- Optional skip report ----
    written_report = None
    if write_skip_report:
        if skip_report_path is None:
            base, _ = os.path.splitext(output_csv_path)
            skip_report_path = f"{base}_skip_report.csv"
        pd.DataFrame(skips, columns=["filename", "phase", "reason", "details"]).to_csv(skip_report_path, index=False)
        written_report = skip_report_path

    # ---- Summary ----
    print("=== Summary ===")
    print(f"Source '*base.png' occurrences: {total_candidates}")
    print(f"Unique basenames in source: {len(src_map)}")
    print(f"Eligible candidates (unique in source & single CSV row): {len(candidates)}")
    print(f"Successfully copied images: {len(copied)} -> {destination_folder}")
    print(f"Filtered CSV written: {output_csv_path} ({len(filtered)} rows)")
    if written_report:
        print(f"Skip report: {written_report}")

if __name__ == "__main__":
    # Example:
    # copy_and_filter_maximize_1to1(
    #     r"C:\path\to\images",
    #     r"C:\path\to\dest",
    #     r"C:\path\to\metadata.csv",
    #     r"C:\path\to\filtered_metadata.csv",
    # )
    pass
