#!/usr/bin/env python3
"""
Clean VLM-generated requests inside JSON/JSONL by editing ONLY the 'value' field.

Defaults:
- Input file: input.json
- Output file: input_cleaned.json (or input_cleaned.jsonl if --jsonl)
- Only clean the JSON key 'value' (can add more with --only-keys).

Removals / Normalization:
- Remove full lines that start with 'Hint:' (case-insensitive, bold allowed).
- Remove 'Question:' / 'Options:' markers (incl. bold **Question:**/**Options:**), leaving a single space.
- Remove inline 'Answer: ...' from the marker to the end of the value.
- NEW: If 'Question:' appears and there is any text between the first '<image>\\n' and the 'Question:' marker,
       delete that entire span (from just after '<image>\\n' through the 'Question:' marker), preserving '<image>\\n'.
- Keep the newline after '<image>' intact.
- Collapse 3+ newlines to exactly 2.
- Collapse double newlines to a single newline when followed by option markers (A / A. / A) / 1 / 1. / 1) …).
- Collapse multiple spaces/tabs to one (do not touch newlines).
- Final pass: remove all asterisks '*' from the cleaned value.

Usage:
  python clean_targets.py                # cleans input.json → input_cleaned.json
  python clean_targets.py --jsonl        # cleans input.json → input_cleaned.jsonl
  python clean_targets.py --file data.json
  python clean_targets.py --file data.json --only-keys value --only-keys text
"""

import argparse
import json
import re
import sys
from typing import Any, List, Optional, Set

# Boilerplate phrases to strip only at the very start of the value
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

# Markers / segments
QUESTION_MARKER_RE = re.compile(r"(?is)\*{0,2}\s*question\s*\*{0,2}\s*:\s*")
OPTIONS_MARKER_RE  = re.compile(r"(?is)\*{0,2}\s*options?\s*\*{0,2}\s*:\s*")
ANSWER_SEGMENT_RE  = re.compile(r"(?is)\*{0,2}\s*answer\s*\*{0,2}\s*:\s*.*$")
HINT_LINE_RE       = re.compile(r"(?im)^\s*\*{0,2}\s*hint\s*\*{0,2}\s*:\s*.*?$")

# Remove from just after "<image>\n" through the Question: marker (if present)
# Keeps the "<image>\n" part intact, deletes any interstitial junk and the Question: marker itself.
AFTER_IMAGE_TO_QUESTION_RE = re.compile(
    r'(?is)(<image>\s*)(?:.*?)(?:\*{0,2}\s*question\s*\*{0,2}\s*:\s*)'
)

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

def normalize_whitespace(text: str) -> str:
    """
    Gentle whitespace normalization:

      1) Preserve the newline immediately after <image>.
      2) Collapse 3+ newlines -> exactly 2 newlines.
      3) Collapse double newlines -> single newline when followed by an option marker:
         - Letter with or without dot/parenthesis (A / A. / A) / a), etc.)
         - Number with or without dot/parenthesis (1 / 1. / 1) …)
      4) Collapse runs of spaces/tabs into one.
      5) Preserve single newlines elsewhere.
    """
    # 1) Protect "<image>\n"
    text = re.sub(r"(<image>)\n", r"\1<<KEEPNEWLINE>>", text)

    # 2) 3+ newlines -> 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 3) Special: double newline before option markers -> single newline
    text = re.sub(
        r"\n\n(?=(?:[A-Za-z]|[0-9]+)(?:[.)](?=\s|$)|(?=\s|$)))",
        "\n",
        text,
    )

    # 4) Collapse multiple spaces/tabs (do NOT touch newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 5) Restore protected "<image>\n"
    text = text.replace("<<KEEPNEWLINE>>", "\n")

    return text

def pre_question_cleanup(content: str) -> str:
    """
    If there is a '<image>\\n ... Question:' pattern, remove everything between
    '<image>\\n' and the Question: marker (inclusive), preserving '<image>\\n'.
    """
    # Replace the span with just the '<image>\\n' we captured
    return AFTER_IMAGE_TO_QUESTION_RE.sub(r"\1", content)

def post_clean(content: str, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    # Remove entire 'Answer: ...' to end of content
    if remove_answer:
        content = ANSWER_SEGMENT_RE.sub("", content)

    # Remove full 'Hint:' lines
    if remove_hint:
        content = HINT_LINE_RE.sub("", content)

    # Replace Question:/Options: markers with a space (so no '**' remains)
    if remove_markers:
        content = QUESTION_MARKER_RE.sub(" ", content)
        content = OPTIONS_MARKER_RE.sub(" ", content)

    return content

def clean_value(text: str, strip_re, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    # 0) Targeted removal between <image>\n and Question: (marker inclusive)
    text = pre_question_cleanup(text)

    # 1) Strip boilerplate phrases if they are at the very start
    prev = None
    while prev != text:
        prev = text
        text = strip_re.sub("", text).lstrip()

    # 2) Remove markers/answers/hints
    text = post_clean(text, remove_markers, remove_answer, remove_hint)

    # 3) Trim quotes/outer spaces
    text = text.strip().strip("“”\"' \t")

    # 4) Gentle whitespace normalization (preserves <image>\n, fixes option spacing)
    text = normalize_whitespace(text)

    # 5) Final pass: remove all asterisks
    text = text.replace("*", "")

    return text

def walk_clean(obj: Any, strip_re, remove_markers: bool, remove_answer: bool, remove_hint: bool, only_keys: Optional[Set[str]]) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and (not only_keys or k in only_keys):
                out[k] = clean_value(v, strip_re, remove_markers, remove_answer, remove_hint)
            else:
                out[k] = walk_clean(v, strip_re, remove_markers, remove_answer, remove_hint, only_keys)
        return out
    if isinstance(obj, list):
        arr = []
        for item in obj:
            if isinstance(item, str) and not only_keys:
                arr.append(clean_value(item, strip_re, remove_markers, remove_answer, remove_hint))
            else:
                arr.append(walk_clean(item, strip_re, remove_markers, remove_answer, remove_hint, only_keys))
        return arr
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
    # Default out path is '<base>_cleaned.<ext>'
    if "." in in_path:
        base, ext = in_path.rsplit(".", 1)
        # If user passes --jsonl but file ext isn't jsonl, we still suffix _cleaned with same ext.
        out_path = f"{base}_cleaned.{ext}"
        if args.jsonl and ext.lower() != "jsonl":
            # Optional: if you want to force .jsonl when --jsonl is set, uncomment next line:
            # out_path = f"{base}_cleaned.jsonl"
            pass
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
