# Matches "Question:", "Question :", "**Question:**", "** Question **:", etc.
QUESTION_MARKER_RE = re.compile(r"(?is)\*{0,2}\s*question\s*\*{0,2}\s*:\s*")

# Matches "Options:", "Option :", "**Options:**", "** Options **:", etc.
OPTIONS_MARKER_RE  = re.compile(r"(?is)\*{0,2}\s*options?\s*\*{0,2}\s*:\s*")
