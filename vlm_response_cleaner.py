#!/usr/bin/env python3
"""
Clean VLM-generated requests by stripping boilerplate phrases from the content
after target prefixes like 'image:' inside string fields of a JSON/JSONL file.

- Input: single file path (--file path/to/data.json or data.jsonl)
- Output: same name with '_cleaned' before extension (e.g., data_cleaned.json)

Supports:
- JSON arrays/objects
- JSONL (line-delimited) with --jsonl
- Custom target labels (--target), default is 'image'
- Extra boilerplate phrases (--extra, --extra-file)

Example:
  python clean_targets.py --file requests.json
  python clean_targets.py --file requests.jsonl --jsonl --target image --target prompt
"""

import argparse
import json
import re
import sys
from typing import Any, List

DEFAULT_PHRASES = [
    r"sure[,!\.]?\s*here\s+is\s+(?:your|the)\s+(?:generated\s+)?text",
    r"sure[,!\.]?",
    r"here\s+is\s+(?:your|the)\s+(?:generated\s+)?text",
    r"here\s+you\s+go",
    r"absolutely[,!\.]?",
    r"of\s+course[,!\.]?",
    r"no\s+problem[,!\.]?",
    r"happy\s+to\s+help[,!\.]?",
    r"as\s+requested[,!\.]?",
    r"certainly[,!\.]?",
    r"okay[,!\.]?",
    r"ok[,!\.]?",
    r"great[,!\.]?",
    r"sure\s+thing[,!\.]?",
]

WS_RE = re.compile(r"\s+")


def load_extra_phrases(path: str) -> List[str]:
    phrases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            phrases.append(s)
    return phrases


def build_strip_regex(phrases: List[str]) -> re.Pattern:
    alt = "|".join([f"(?:{p})" for p in phrases]) if phrases else r"(?!x)x"
    pat = rf"^(?:{alt})[ \t\-\–\—\:\;\,\.\!\?\"\'\)\(]*"
    return re.compile(pat, flags=re.IGNORECASE)


def compile_combined_regex(targets: List[str]) -> re.Pattern:
    targ_alt = "|".join([re.escape(t) for t in targets])
    pattern = rf"(?is)(?P<label>\b(?P<name>{targ_alt})\s*:\s*)(?P<content>.*?)(?=(?:\b(?:{targ_alt})\s*:\s*)|$)"
    return re.compile(pattern)


def clean_one_string(text: str, combined_re: re.Pattern, strip_re: re.Pattern) -> str:
    def repl(m: re.Match) -> str:
        label_full = m.group("label")
        name = m.group("name")
        content = m.group("content")

        prev = None
        while prev != content:
            prev = content
            content = strip_re.sub("", content).lstrip()

        content = content.strip().strip("“”\"' \t")
        content = WS_RE.sub(" ", content)

        return f"{name.lower()}: {content}"

    return combined_re.sub(repl, text)


def walk_clean(obj: Any, combined_re: re.Pattern, strip_re: re.Pattern) -> Any:
    if isinstance(obj, dict):
        return {k: walk_clean(v, combined_re, strip_re) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk_clean(v, combined_re, strip_re) for v in obj]
    if isinstance(obj, str):
        return clean_one_string(obj, combined_re, strip_re)
    return obj


def process_json(in_path: str, out_path: str, is_jsonl: bool, targets: List[str], phrases: List[str]) -> None:
    combined_re = compile_combined_regex(targets)
    strip_re = build_strip_regex(phrases)

    if is_jsonl:
        with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
            for line in fin:
                raw = line.rstrip("\n")
                if not raw.strip():
                    fout.write("\n")
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    fout.write(line)
                    continue
                cleaned = walk_clean(record, combined_re, strip_re)
                fout.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    else:
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cleaned = walk_clean(data, combined_re, strip_re)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)


def main():
    p = argparse.ArgumentParser(description="Clean boilerplate after target prefixes (e.g., 'image:') in JSON/JSONL files.")
    p.add_argument("--file", required=True, help="Input .json or .jsonl file path")
    p.add_argument("--jsonl", action="store_true", help="Treat input as JSON Lines (.jsonl)")
    p.add_argument("--target", action="append", default=[], help="Target label to clean (default: image). Repeatable.")
    p.add_argument("--extra", action="append", default=[], help="Extra phrase (regex) to strip. Repeatable.")
    p.add_argument("--extra-file", help="File with regexes, one per line (comments with #).")

    args = p.parse_args()

    in_path = args.file
    # Make output path with "_cleaned" before extension
    if "." in in_path:
        base, ext = in_path.rsplit(".", 1)
        out_path = f"{base}_cleaned.{ext}"
    else:
        out_path = in_path + "_cleaned"

    targets = [t.strip() for t in (args.target or []) if t.strip()]
    if not targets:
        targets = ["image"]

    phrases = DEFAULT_PHRASES.copy()
    if args.extra_file:
        phrases.extend(load_extra_phrases(args.extra_file))
    if args.extra:
        phrases.extend(args.extra)

    try:
        process_json(in_path, out_path, args.jsonl, targets, phrases)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Cleaned file written to: {out_path}")


if __name__ == "__main__":
    main()