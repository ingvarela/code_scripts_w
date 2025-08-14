Before (what you have now):

python
Copy
Edit
drawn_text = "\n".join(lines_draw)
draw.multiline_text((10,10), drawn_text, font=font, fill=font_color, spacing=spacing)
# expected_ocr = drawn_text  # (your current OCR rule)
After (center each line):

python
Copy
Edit
# horizontal centering draw (respects margins and max_text_width)
left_margin  = 10
right_margin = 10
max_line_w = CW - (left_margin + right_margin)

y = 10
lh = line_height_of(font)
centered_lines = []

for line in lines_draw:
    # measure this line
    w = draw.textbbox((0,0), line, font=font)[2]
    # center within usable width
    x = left_margin + max(0, (max_line_w - w) // 2)
    draw.text((x, y), line, font=font, fill=font_color)
    centered_lines.append(line)
    y += lh + spacing

# keep OCR exactly what was actually drawn
drawn_text = "\n".join(centered_lines)
expected_ocr = drawn_text
why this works: you already wrapped to max_text_width = CW - 20. the centering uses the same interior width (10 + 10 margins), so nothing spills.

2) (Optional) gently widen lines by adding extra spaces between words—but never exceed the canvas
If you also want lines to look a tad more “stretched” horizontally (without full justification), insert a few extra spaces between words only when they still fit. Since you’re saving expected_ocr = drawn_text, the OCR will include those added spaces (1:1 with the image), which is what you asked for.

A) Add this tiny helper near your other helpers:

python
Copy
Edit
def widen_line_with_spaces(line: str, draw, font, max_width: int, rng) -> str:
    """
    Try to visually widen a line by sprinkling a few extra spaces between words,
    but never exceed max_width. Returns the (possibly) widened line.
    """
    parts = line.split(" ")
    if len(parts) <= 1:
        return line

    # candidate insertion indices (between words)
    gaps = list(range(1, len(parts)))
    rng.shuffle(gaps)

    widened = parts[:]  # copy
    # attempt up to a few insertions (tunable)
    attempts = min(4, len(gaps))
    for i in range(attempts):
        g = gaps[i]
        # insert one extra space at gap g
        widened[g-1] = widened[g-1] + " "
        candidate = " ".join(widened)
        w = draw.textbbox((0,0), candidate, font=font)[2]
        if w > max_width:
            # revert this insertion if it overflows
            widened[g-1] = widened[g-1].rstrip()
        # else keep it and continue to next gap
    return " ".join(widened)
B) Use it right before drawing (in the centering loop):
Replace the centering loop above with this version that widens lines first:

python
Copy
Edit
left_margin  = 10
right_margin = 10
max_line_w = CW - (left_margin + right_margin)

y = 10
lh = line_height_of(font)
centered_lines = []

for line in lines_draw:
    # (optional) gently widen the line with a few extra spaces if it still fits
    line_wide = widen_line_with_spaces(line, draw, font, max_line_w, rng)

    w = draw.textbbox((0,0), line_wide, font=font)[2]
    x = left_margin + max(0, (max_line_w - w) // 2)
    draw.text((x, y), line_wide, font=font, fill=font_color)
    centered_lines.append(line_wide)
    y += lh + spacing

drawn_text = "\n".join(centered_lines)
expected_ocr = drawn_text
knobs: attempts = min(4, len(gaps)) controls how much widening to try. set to 2 for even subtler effect.
