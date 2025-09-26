# Remove "Fill in the blank" when it appears at the start of a line
FILL_IN_BLANK_AFTER_NL_RE = re.compile(
    r'(?im)(?:^|(?<=\n))\s*\*{0,2}\s*fill\s*in\s*the\s*blank\s*\*{0,2}\s*:?\s*'
)


def post_clean(content: str, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    if remove_answer:
        content = ANSWER_SEGMENT_RE.sub("", content)
    if remove_hint:
        content = HINT_LINE_RE.sub("", content)
    if remove_markers:
        content = QUESTION_MARKER_RE.sub(" ", content)
        content = OPTIONS_MARKER_RE.sub(" ", content)

    # NEW: remove "Fill in the blank" lines/phrases at line start
    content = FILL_IN_BLANK_AFTER_NL_RE.sub("", content)

    return content
