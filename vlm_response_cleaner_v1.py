#!/usr/bin/env python3
"""
Clean VLM-generated requests by stripping boilerplate phrases from the content
after target prefixes like 'image:' inside string fields of a JSON/JSONL file.

- Input: single file path (--file path/to/data.json or data.jsonl)
- Output: same name with '_cleaned' before extension (e.g., data_cleaned.json)

Features:
- JSON (.json) and JSONL (.jsonl via --jsonl)
- Custom target labels (--target); default is 'image'
- Extra boilerplate phrases (--extra, --extra-file)
- NEW: remove label markers "Question:" / "Options:" (incl. bold **Question:**/**Options:**) by default
- NEW: remove entire "Answer: ..." segment to the end of the target content by default
- Toggle with --keep-markers and --keep-answer

Examples:
  python clean_targets.py --file requests.json
  python clean_targets.py --file requests.jsonl --jsonl --target image --target prompt
"""

import argparse
import json
import re
import sys
from typing import Any, List

# Default boilerplate phrases removed only at the very start of the target content
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

# Marker regexes:
# Matches "Question:" / "**Question:**" / "  Question  :  " etc., case-insensitive
QUESTION_MARKER_RE = re.compile(r"(?is)\*{0,2}\s*question\s*\*{0,2}\s*:\s*")
OPTIONS_MARKER_RE  = re.compile(r"(?is)\*{0,2}\s*options?\s*\*{0,2}\s*:\s*")
# Remove entire "Answer: ..." segment (bold allowed). DOTALL to end of content.
ANSWER_SEGMENT_RE  = re.compile(r"(?is)\*{0,2}\s*answer\s*\*{0,2}\s*:\s*.*$")


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
    # Find segments like: "<label> : <content until next label or end>"
    targ_alt = "|".join([re.escape(t) for t in targets])
    pattern = rf"(?is)(?P<label>\b(?P<name>{targ_alt})\s*:\s*)(?P<content>.*?)(?=(?:\b(?:{targ_alt})\s*:\s*)|$)"
    return re.compile(pattern)


def post_clean_markers_and_answer(content: str, remove_markers: bool, remove_answer: bool) -> str:
    """
    Additional cleaning inside the target content:
      - Remove Question:/Options: markers (incl. bold variants) if remove_markers=True
      - Remove entire 'Answer: ...' to the end if remove_answer=True
    """
    if remove_answer:
        content = ANSWER_SEGMENT_RE.sub("", content)

    if remove_markers:
        # Remove all occurrences of these markers wherever they appear
        content = QUESTION_MARKER_RE.sub("", content)
        content = OPTIONS_MARKER_RE.sub("", content)

    return content


def clean_one_string(
    text: str,
    combined_re: re.Pattern,
    strip_re: re.Pattern,
    remove_markers: bool,
    remove_answer: bool,
) -> str:
    def repl(m: re.Match) -> str:
        # label_full = m.group("label")  # not used, we standardize to lowercase label
        name = m.group("name")
        content = m.group("content")

        # 1) Strip boilerplate at the very start (repeat until stable)
        prev = None
        while prev != content:
            prev = content
            content = strip_re.sub("", content).lstrip()

        # 2) Remove markers and/or answer segment as requested
        content = post_clean_markers_and_answer(content, remove_markers, remove_answer)

        # 3) Normalize whitespace and trim wrapping quotes
        content = content.strip().strip("“”\"' \t")
        content = WS_RE.sub(" ", content)

        # 4) Rebuild with standardized lowercase prefix
        return f"{name.lower()}: {content}"

    return combined_re.sub(repl, text)


def walk_clean(
    obj: Any,
    combined_re: re.Pattern,
    strip_re: re.Pattern,
    remove_markers: bool,
    remove_answer: bool,
) -> Any:
    if isinstance(obj, dict):
        return {k: walk_clean(v, combined_re, strip_re, remove_markers, remove_answer) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk_clean(v, combined_re, strip_re, remove_markers, remove_answer) for v in obj]
    if isinstance(obj, str):
        return clean_one_string(obj, combined_re, strip_re, remove_markers, remove_answer)
    return obj


def process_json(
    in_path: str,
    out_path: str,
    is_jsonl: bool,
    targets: List[str],
    phrases: List[str],
    remove_markers: bool,
    remove_answer: bool,
) -> None:
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
                    # Not valid JSON line: keep unchanged
                    fout.write(line)
                    continue
                cleaned = walk_clean(record, combined_re, strip_re, remove_markers, remove_answer)
                fout.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    else:
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cleaned = walk_clean(data, combined_re, strip_re, remove_markers, remove_answer)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)


def main():
    p = argparse.ArgumentParser(description="Clean boilerplate after target prefixes (e.g., 'image:') in JSON/JSONL files.")
    p.add_argument("--file", required=True, help="Input .json or .jsonl file path")
    p.add_argument("--jsonl", action="store_true", help="Treat input as JSON Lines (.jsonl)")
    p.add_argument("--target", action="append", default=[], help="Target label to clean (default: image). Repeatable.")
    p.add_argument("--extra", action="append", default=[], help="Extra phrase (regex) to strip. Repeatable.")
    p.add_argument("--extra-file", help="File with regexes, one per line (comments with #).")

    # Toggles for new behavior (both enabled by default)
    p.add_argument("--keep-markers", action="store_true", help="Keep 'Question:'/'Options:' markers (do not remove).")
    p.add_argument("--keep-answer", action="store_true", help="Keep 'Answer: ...' segments (do not remove).")

    args = p.parse_args()

    in_path = args.file
    # Output path with "_cleaned" before extension
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
