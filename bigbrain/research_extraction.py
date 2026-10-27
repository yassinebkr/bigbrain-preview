"""HTML block extraction and literal text windows for research evidence.

Aligns Trafilatura output to original DOM blocks, restores table structure and
preserves code, heading context and source locations for stored observations.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET


def normalized(text):
    return " ".join(text.split())


def extract_html(html: str, url: str) -> dict:
    try:
        from bs4 import BeautifulSoup, NavigableString, Comment, Doctype, Declaration, ProcessingInstruction
        import trafilatura
    except ImportError:
        # Preserve baseline capability when the optional research extra is absent,
        # but never silently advertise the stronger structural extraction.
        from .research import TextExtractor
        parser = TextExtractor()
        parser.feed(html)
        blocks = [{"id": "b1", "text": "\n".join(parser.parts), "kind": "unfiltered_text",
                   "locator": "HTMLParser:data-stream", "context": []}]
        return {"blocks": blocks, "original_blocks": blocks, "title": "", "outline": [],
                "links": parser.links, "has_scripts": "<script" in html.lower(), "engine": "stdlib-fallback",
                "limitations": ["Install .[research] for source-aligned table/code extraction; unfiltered text fallback used"]}

    soup = BeautifulSoup(html, "html.parser")
    has_scripts = bool(soup.find("script"))
    title = soup.title.get_text(" ", strip=True)[:500] if soup.title else ""
    for hidden in soup.select("script, style, noscript, template, [hidden], [aria-hidden='true']"):
        hidden.decompose()
    root = soup.body or soup
    links = [a["href"] for a in root.select("a[href]")]
    originals, outline, headings = [], [], []
    entry_anchor = None
    section_id = None
    consumed = set()
    block_tags = {"p", "pre", "li", "tr", "caption", "dt", "h", "h1", "h2", "h3", "h4", "h5", "h6"}
    # Walk source order so plain aside/footer text also enters the original
    # evidence index. Such text can contain a qualification outside a paragraph.
    for element in root.descendants:
        if isinstance(element,(Comment,Doctype,Declaration,ProcessingInstruction)):
            continue
        if any(id(parent) in consumed for parent in element.parents):
            continue
        if (getattr(element, 'name', None) == 'a' and element.get('name')
                and not element.get('href') and not element.get_text(strip=True)):
            # Dedicated named anchors mark reference entries even when the
            # publisher uses plain paragraphs instead of semantic headings.
            entry_anchor = '#' + element['name']
            section_id = element['name']
            continue
        if isinstance(element,NavigableString):
            text,kind = str(element).strip(),"text"
            if not text:
                continue
        elif element.name not in block_tags:
            continue
        elif element.name in {"p","li"} and element.find(list(block_tags)):
            # Nested paragraphs/lists are visited individually, preserving code
            # and tables rather than flattening their containing list item.
            continue
        else:
            # Some reference generators emit <h> entry headings. Preserve
            # their labels and boundaries using the ordinary heading path.
            kind = 'h3' if element.name == 'h' else element.name
            consumed.add(id(element))
        if kind.startswith("h") and len(kind) == 2 and kind[1].isdigit():
            level = int(kind[1])
            headings = [(l, t) for l, t in headings if l < level]
            headings.append((level, element.get_text(" ", strip=True)))
            outline.append({"level": level, "text": headings[-1][1]})
            section_id = element.get('id') or element.get('_id') or (entry_anchor[1:] if entry_anchor else None)
            entry_anchor = None
        if kind == "tr":
            text = " | ".join(c.get_text(" ", strip=True) for c in element.find_all(["td", "th"], recursive=False))
            kind = "table_row"
        elif kind == "pre":
            text, kind = element.get_text().strip("\n"), "code"
        elif kind != "text":
            text = element.get_text(" ", strip=True)
        if text.strip():
            context = [t for _, t in headings]
            if entry_anchor:
                context.append(entry_anchor)
            definition = element if kind == "dt" else None
            if definition is None:
                description = element.find_parent("dd")
                if description is not None:
                    definition = description.find_previous_sibling("dt")
            if definition is not None:
                # Consecutive terms in a definition list share the following
                # description. Assign aliases one context so a focused term
                # retains that description and its qualifications.
                first = definition
                while (previous := first.find_previous_sibling()) is not None and previous.name == 'dt':
                    first = previous
                terms, current = [], first
                while current is not None and current.name == 'dt':
                    terms.append(current.get_text(' ', strip=True))
                    current = current.find_next_sibling()
                context.append(' | '.join(terms))
            originals.append({"id": f"b{len(originals)+1}", "text": text, "kind": kind,
                              "locator": f"observed-dom:block[{len(originals)}]",
                              "context": context, "section_id": section_id})
    if not originals:
        text = root.get_text(" ", strip=True)
        if text:
            originals.append({"id": "b1", "text": text, "kind": "text", "locator": "observed-dom:body", "context": []})

    limitations = []
    xml = trafilatura.extract(html, url=url, output_format="xml", favor_recall=True,
                              include_tables=True, include_comments=False, include_links=True, deduplicate=False)
    chosen = set()
    if xml:
        main = ET.fromstring(xml).find("main")
        if main is not None:
            for node in main.iter():
                if node.tag not in {"p", "head", "code", "quote", "item", "row"}:
                    continue
                text = (" | ".join("".join(c.itertext()).strip() for c in node)
                        if node.tag == "row" else "".join(node.itertext()))
                text = normalized(text)
                matches = [b for b in originals if normalized(b["text"]) == text]
                # Caption padding is accepted only after an actual caption match.
                if not matches and node.tag == "row":
                    cells = [c.strip() for c in text.split("|") if c.strip()]
                    if len(cells) == 1:
                        matches = [b for b in originals if b["kind"] == "caption" and normalized(b["text"]) == cells[0]]
                if matches:
                    chosen.add(matches[0]["id"])
                elif text:
                    limitations.append("An extracted block could not be aligned; original DOM fallback retained")
    if not chosen or limitations:
        chosen = {b["id"] for b in originals}
        if not xml:
            limitations.append("Main-text extraction empty; original DOM fallback retained")
    # Preserve every original table row, including empty cells. Table omission
    # cannot be treated as query-relevance selection at this acquisition stage.
    recovered = [b for b in originals if b["kind"] in {"table_row", "caption"} and b["id"] not in chosen]
    chosen.update(b["id"] for b in recovered)
    if recovered:
        limitations.append("Original table structure restored where main-text extraction omitted rows")
    if len(chosen) < len(originals):
        limitations.append("Main-text extraction omits DOM blocks; original block artifact remains available")
    if has_scripts:
        limitations.append("HTTP DOM alone does not establish JavaScript-rendered content")
    return {"blocks": [b for b in originals if b["id"] in chosen], "original_blocks": originals,
            "title": title, "outline": outline, "links": links, "has_scripts": has_scripts,
            "engine": "trafilatura-recall-source-aligned", "limitations": list(dict.fromkeys(limitations))}


def window(blocks: list[dict], focus: str | None = None, limit: int = 12000) -> tuple[list[dict], bool]:
    """Literal windows with preserved source-block identities and explicit clipping."""
    full = "\n".join(b["text"] for b in blocks)
    start = 0
    section_end = len(full)
    if focus:
        # API definition signatures and headings take precedence over links in
        # indexes or comparison tables. Match against the entire original index.
        candidates, offset = [], 0
        for block in blocks:
            pattern = re.escape(focus).replace(r"\.", r"\s*\.\s*")
            for match in re.finditer(pattern, block["text"], re.IGNORECASE):
                definition = block["kind"] == "dt"
                heading = bool(re.fullmatch(r"h[1-6]", block["kind"]))
                exact = bool(re.fullmatch(pattern, block["text"].strip(), re.IGNORECASE))
                # A dedicated entry outranks an occurrence inside a longer
                # signature or synopsis. Preserve source order for equal ranks.
                priority = 4 if exact and definition else 3 if exact and heading else 2 if definition else 1 if heading else 0
                candidates.append((priority, -(offset + match.start()), offset + match.start()))
            offset += len(block["text"]) + 1
        if not candidates:
            raise ValueError("Requested literal focus was not found in the page")
        position = max(candidates)[2]
        start = max(0, position - 500)
        offset = 0
        for i, block in enumerate(blocks):
            if offset <= position < offset + len(block["text"]):
                # A match inside a definition's prose needs its complete local
                # conditions and label. Recover the enclosing contiguous entry.
                first = i
                while first > 0 and blocks[first-1].get("context") == block.get("context"):
                    first -= 1
                definition = any(b["kind"] == "dt" for b in blocks[first:i+1])
                heading = bool(re.fullmatch(r"h[1-6]", blocks[first]["kind"]))
                if not definition and not heading:
                    break
                # A definition's conditions and version notes share its context.
                # Keep the complete entry up to the next definition/section.
                start = offset - sum(len(b["text"]) + 1 for b in blocks[first:i])
                section_end = offset + len(block["text"])
                for following in blocks[i+1:]:
                    context = block.get("context", [])
                    following_context = following.get("context", [])
                    if (following_context != context if definition else
                            following_context[:len(context)] != context):
                        break
                    section_end += 1 + len(following["text"])
                # Oversized sections still center the observed literal match;
                # clipping remains explicit on the returned source blocks.
                if position >= start + limit:
                    start = max(start, position - 500)
                break
            offset += len(block["text"]) + 1
    end, offset, selected = min(start + limit, section_end), 0, []
    for block in blocks:
        length = len(block["text"])
        left, right = max(0, start-offset), min(length, end-offset)
        if left < right:
            selected.append({**block, "text": block["text"][left:right], "clipped": left > 0 or right < length,
                             "block_start": left, "block_end": right})
        offset += length + 1
    return selected, start > 0 or len(full) > end
