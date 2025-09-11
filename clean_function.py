def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace gently:
      - Collapse 3+ newlines into 2 newlines.
      - Collapse runs of spaces/tabs into a single space.
      - Preserve single newlines.
      - Do NOT strip newline after <image>.
    """
    # Protect <image>\n by temporarily marking it
    text = re.sub(r"(<image>)\n", r"\1<<KEEPNEWLINE>>", text)

    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces/tabs into one
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Restore the protected <image>\n
    text = text.replace("<<KEEPNEWLINE>>", "\n")

    return text


def clean_value(text: str, strip_re, remove_markers: bool, remove_answer: bool, remove_hint: bool) -> str:
    prev = None
    while prev != text:
        prev = text
        text = strip_re.sub("", text).lstrip()

    text = post_clean(text, remove_markers, remove_answer, remove_hint)
    text = text.strip().strip("“”\"' \t")

    # Instead of collapsing ALL whitespace, normalize gently
    text = normalize_whitespace(text)

    return text
