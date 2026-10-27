"""Resolve research quotations to offsets in the original observed passage."""
import re


def whitespace_view(text):
    """Collapse whitespace while mapping each character to its original span."""
    characters, starts, ends = [], [], []
    for match in re.finditer(r"\s+|\S", text):
        characters.append(" " if match.group().isspace() else match.group())
        starts.append(match.start())
        ends.append(match.end())
    return "".join(characters), starts, ends


def anchor_quote(text, supplied, start=None, end=None):
    """Return the exact original quote and its unique half-open character span.

    Only whitespace presentation may differ. Case, punctuation, word order and
    word boundaries remain part of matching. Explicit spans resolve repetition.
    """
    normalized, starts, ends = whitespace_view(text)
    expected = whitespace_view(supplied)[0].strip()
    if not expected:
        raise ValueError("Quotation is empty after whitespace normalization")
    if start is not None or end is not None:
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(text)):
            raise ValueError("Quotation offsets must identify a valid original span")
        if whitespace_view(text[start:end])[0].strip() != expected:
            raise ValueError("Quotation offsets disagree with the observed text")
        return text[start:end], start, end
    matches = []
    position = normalized.find(expected)
    while position >= 0:
        matches.append((starts[position], ends[position+len(expected)-1]))
        position = normalized.find(expected, position+1)
    if len(matches) != 1:
        raise ValueError("Quotation must match one original span; provide offsets for repeated text")
    start, end = matches[0]
    return text[start:end], start, end
