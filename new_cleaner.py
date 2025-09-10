#!/usr/bin/env python3
"""
Clean VLM-generated requests inside JSON/JSONL by editing ONLY the 'value' field.

Defaults:
- Input file: input.json
- Output file: input_cleaned.json (or input_cleaned.jsonl if --jsonl)
- Only clean the JSON key 'value' (can add more with --only-keys).
- Remove full lines that start with 'Hint:'.
- Remove 'Question:' / 'Options:' markers (including bold).
- Remove inline 'Answer: ...' (to the end of the same string).
- Strip common polite boilerplate at the very start.

Usage:
  python clean_targets.py                # cleans input.json → input_cleaned.json
  python clean_targets.py --jsonl        # cleans input.json → input_cleaned.jsonl
  python clean_targets.py --file data.json --only-keys value
"""

import argparse
import json
import re
import sys
from typing import Any, List, Optional, Set

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

QUESTION_MARKER_RE = re.compile(r"(?is)\*{0,2}\s*question\s*\*{0,2}\s*:\s*")
OPTIONS_MARKER_RE  = re.compile(r"(?is)\*{0,2}\s*options?\s*\*{0,2}\s*:\s*")
ANSWER_SEGMENT_RE  = re.compile(r"(?is)\*{0,2}\s*answer\s*\*{0,2}\s*:\s*.*$")
HINT_LINE_RE       = re.compile(r"(?im)^\s*\*{0,2}\s*hint\s*\*{0,2}\s*:\s*.*?$")

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

def post_clean(content: str, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    if remove_answer:
        content = ANSWER_SEGMENT_RE.sub("", content)
    if remove_hint:
        content = HINT_LINE_RE.sub("", content)
    if remove_markers:
        content = QUESTION_MARKER_RE.sub("", content)
        content = OPTIONS_MARKER_RE.sub("", content)
    return content

def clean_value(text: str, strip_re, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    prev = None
    while prev != text:
        prev = text
        text = strip_re.sub("", text).lstrip()

    text = post_clean(text, remove_markers, remove_answer, remove_hint)
    text = text.strip().strip("“”\"' \t")
    text = WS_RE.sub(" ", text)
    return text

def walk_clean(obj: Any, strip_re, remove_markers: bool, remove_answer: bool, remove_hint: bool, only_keys: Optional[Set[str]]) -> Any:
    if isinstance(obj, dict):
        return {
            k: clean_value(v, strip_re, remove_markers, remove_answer, remove_hint)
            if isinstance(v, str) and (not only_keys or k in only_keys)
            else walk_clean(v, strip_re, remove_markers, remove_answer, remove_hint, only_keys)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            clean_value(item, strip_re, remove_markers, remove_answer, remove_hint)
            if isinstance(item, str) and not only_keys
            else walk_clean(item, strip_re, remove_markers, remove_answer, remove_hint, only_keys)
            for item in obj
        ]
    return obj

def process_json(in_path: str, out_path: str, is_jsonl: bool, phrases: List[str], only_keys: Optional[Set[str]], remove_markers: bool, remove_answer: bool, remove_hint: bool):
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
                cleaned = walk_clean(record, strip_re, remove_markers, remove_answer, remove_hint, only_keys)
                fout.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    else:
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cleaned = walk_clean(data, strip_re, remove_markers, remove_answer, remove_hint, only_keys)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

def main():
    p = argparse.ArgumentParser(description="Clean only the 'value' fields in JSON/JSONL.")
    p.add_argument("--file", default="input.json", help="Input .json or .jsonl file path (default: input.json)")
    p.add_argument("--jsonl", action="store_true", help="Treat input as JSON Lines (.jsonl)")
    p.add_argument("--extra", action="append", default=[], help="Extra phrase (regex) to strip from start. Repeatable.")
    p.add_argument("--extra-file", help="File with regexes, one per line (comments with #).")
    p.add_argument("--only-keys", action="append", default=["value"], help="Only clean values of these keys (default: value)")
    p.add_argument("--keep-markers", action="store_true", help="Keep 'Question:'/'Options:' markers.")
    p.add_argument("--keep-answer", action="store_true", help="Keep 'Answer: ...' segments.")
    p.add_argument("--keep-hint-lines", action="store_true", help="Keep lines starting with 'Hint:'.")

    args = p.parse_args()

    in_path = args.file
    if "." in in_path:
        base, ext = in_path.rsplit(".", 1)
        out_path = f"{base}_cleaned.{ext}"
    else:
        out_path = in_path + "_cleaned"

    phrases = DEFAULT_PHRASES.copy()
    if args.extra_file:
        phrases.extend(load_extra_phrases(args.extra_file))
    if args.extra:
        phrases.extend(args.extra)

    only_keys = set(args.only_keys) if args.only_keys else None
    remove_markers = not args.keep_markers
    remove_answer = not args.keep_answer
    remove_hint = not args.keep_hint_lines

    try:
        process_json(in_path, out_path, args.jsonl, phrases, only_keys, remove_markers, remove_answer, remove_hint)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Cleaned file written to: {out_path}")

if __name__ == "__main__":
    main()
