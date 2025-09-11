def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace gently:
      - Collapse 3+ newlines into 2 newlines.
      - Collapse double newlines into a single one *if followed by option markers (A., B., C., 1., etc.)*.
      - Collapse runs of spaces/tabs into a single space.
      - Preserve single newlines.
      - Do NOT strip newline after <image>.
    """
    # Protect <image>\n
    text = re.sub(r"(<image>)\n", r"\1<<KEEPNEWLINE>>", text)

    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Special: collapse double newlines before option markers into single
    text = re.sub(r"\n\n(?=[A-Z0-9]\.)", "\n", text)

    # Collapse multiple spaces/tabs
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Restore protected <image>\n
    text = text.replace("<<KEEPNEWLINE>>", "\n")

    return text
