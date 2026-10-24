"""Phase 2 offline comparison. Adapters never receive questions or gold labels.

Use an isolated environment with requirements-phase2.lock. JSON output retains
candidate blocks and observation hashes so coverage can be independently read.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import statistics
import subprocess
import time
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from evaluate import document_html, load, normalize, score, validate


@dataclass
class Extraction:
    blocks: list[dict] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def add(self, text, kind="text", locator=""):
        if text.strip():
            value = text.strip("\n") if kind == "code" else text.strip()
            self.blocks.append({"text": value, "kind": kind, "locator": locator})


def current_extractor(path):
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TextExtractor")
    scope = {"HTMLParser": HTMLParser}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)
    cls = scope["TextExtractor"]

    def extract(html, url):
        parser = cls()
        parser.feed(html)
        result = Extraction(links=[urljoin(url, link) for link in parser.links])
        # One stream mirrors PageReader; it makes no block/row guarantee.
        result.add("\n".join(parser.parts), "visible_text", "HTMLParser:data-stream")
        return result

    return extract


def trafilatura_extractor(mode):
    import trafilatura

    def extract(html, url):
        xml = trafilatura.extract(
            html, url=url, output_format="xml", include_comments=False,
            include_tables=True, include_links=True, deduplicate=False,
            favor_recall=mode == "recall", favor_precision=mode == "precision",
        )
        result = Extraction()
        if not xml:
            result.limitations.append("Extractor returned no content")
            return result
        root = ET.fromstring(xml)
        main = root.find("main")
        if main is None:
            result.limitations.append("Extractor returned no main element")
            return result
        # Preserve atomic code blocks and row associations, rather than flattening
        # the XML. Keep generated presentation distinct from original source HTML.
        def visit(element, locator):
            if element.tag == "row":
                cells = ["".join(cell.itertext()).strip() for cell in element]
                result.add(" | ".join(cells), "table_row", locator)
            elif element.tag in {"code", "head", "p", "item", "quote"}:
                result.add("".join(element.itertext()), element.tag, locator)
            elif len(element):
                if element.text and element.text.strip():
                    result.add(element.text, element.tag, locator + "/text()")
                for index, child in enumerate(element):
                    visit(child, f"{locator}/{child.tag}[{index}]")
                    if child.tail and child.tail.strip():
                        result.add(child.tail, element.tag, locator + "/tail()")
            else:
                result.add(element.text or "", element.tag, locator)
        visit(main, "extracted-xml:/main")
        result.links = list(dict.fromkeys(urljoin(url, ref.attrib["target"])
                                        for ref in main.iter("ref") if "target" in ref.attrib))
        return result

    return extract


def markdownify_extractor(html, url):
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, noscript, template"):
        element.decompose()
    # No nav/aside pruning: this measures conversion, not semantic extraction.
    result = Extraction(links=list(dict.fromkeys(urljoin(url, a["href"])
                                               for a in soup.select("a[href]"))))
    markdown = markdownify(str(soup), heading_style="ATX", escape_underscores=False,
                          escape_asterisks=False)
    in_code, code = False, []
    for index, line in enumerate(markdown.splitlines()):
        locator = f"converted-markdown:line-{index + 1}"
        if line.startswith("```"):
            if in_code:
                result.add("\n".join(code), "code", locator)
                code = []
            in_code = not in_code
        elif in_code:
            code.append(line)
        elif line.startswith("|"):
            if not re.fullmatch(r"[\s|:\-]+", line):
                result.add(line.strip().strip("|").strip(), "table_row", locator)
        else:
            text = re.sub(r"^#{1,6}\s+", "", line)
            # Preserve link destinations separately, keep actual anchor text here.
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
            result.add(text, "text", locator)
    if in_code:
        result.add("\n".join(code), "code", "converted-markdown:unterminated-code")
    return result


def source_grounded_recall(html, url):
    """Prototype: align extracted blocks to observed DOM; reject unsupported ones.

    Trafilatura's XML can pad captions into artificial table rows. Represent a
    proven original caption as a caption, never as a synthetic data row. Other
    alignment failures remain explicit; no unchecked passage is passed onward.
    """
    from bs4 import BeautifulSoup

    result = trafilatura_extractor("recall")(html, url)
    soup = BeautifulSoup(html, "html.parser")
    for hidden in soup.select("script, style, noscript, template"):
        hidden.decompose()
    original = normalize(soup.get_text(" "))
    rows = {}
    captions = {}
    source_code = {}
    for index, code in enumerate(soup.select("pre")):
        raw_code = code.get_text().strip("\n")
        source_code.setdefault(normalize(raw_code), (raw_code, f"observed-dom:pre[{index}]"))
    source_tables = []
    for table in soup.select("table"):
        table_rows = []
        for row in table.find_all("tr"):
            cells = [normalize(c.get_text(" ")) for c in row.find_all(["td", "th"], recursive=False)]
            if cells:
                table_rows.append(" | ".join(cells).strip())
        source_tables.append(table_rows)
    for index, row in enumerate(soup.select("tr")):
        cells = [normalize(c.get_text(" ")) for c in row.find_all(["td", "th"], recursive=False)]
        if cells:
            rows.setdefault(" | ".join(cells).strip(), []).append(f"observed-dom:tr[{index}]")
    for index, caption in enumerate(soup.select("caption")):
        captions.setdefault(normalize(caption.get_text(" ")), []).append(f"observed-dom:caption[{index}]")
    accepted = []
    for block in result.blocks:
        text = normalize(block["text"])
        if block["kind"] == "table_row":
            if text in rows:
                block["source_locations"] = rows[text]
            else:
                nonempty = [v.strip() for v in text.split("|") if v.strip()]
                if len(nonempty) == 1 and nonempty[0] in captions:
                    block = {**block, "text": nonempty[0], "kind": "caption",
                             "source_locations": captions[nonempty[0]],
                             "transformation": "XML caption padding removed after exact observed-caption match"}
                else:
                    result.limitations.append(f"Unaligned extracted table row withheld: {text}")
                    continue
        elif text in source_code:
            raw_code, location = source_code[text]
            block = {**block, "text": raw_code, "kind": "code", "source_locations": [location],
                     "transformation": "Original observed preformatted text retained after normalized match"}
        elif text in original:
            # Offset is in normalized observed visible text, not raw HTML bytes.
            # First occurrence is enough to ground a block, not a uniqueness claim.
            block["source_locations"] = [f"observed-visible-text:{original.index(text)}:{len(text)}"]
        else:
            result.limitations.append(f"Unaligned extracted block withheld: {text}")
            continue
        accepted.append(block)
    result.blocks = accepted
    represented_rows = {normalize(b["text"]) for b in accepted if b["kind"] == "table_row"}
    for table_rows in source_tables:
        if represented_rows.intersection(table_rows):
            for missing in set(table_rows) - represented_rows:
                result.limitations.append(f"Original row missing from a partially extracted table: {missing}")
    return result


def bounded_blocks(blocks, limit):
    """Same newline serialization budget for all candidates, including joins."""
    if limit is None:
        return blocks
    selected, remaining = [], limit
    for block in blocks:
        separator = 1 if selected else 0
        if remaining <= separator:
            break
        text = block["text"][:remaining - separator]
        selected.append({**block, "text": text})
        remaining -= len(text) + separator
    return selected


def run(reader, samples=10):
    corpus = load()
    validate(corpus)
    adapters = {
        "current": current_extractor(reader),
        "trafilatura_default": trafilatura_extractor("default"),
        "trafilatura_recall": trafilatura_extractor("recall"),
        "trafilatura_precision": trafilatura_extractor("precision"),
        "markdownify": markdownify_extractor,
        "trafilatura_recall_grounded": source_grounded_recall,
    }
    # Load packages before timing. Each document is isolated: no cross-document
    # deduplication/cache can make independent runs lose content.
    for adapter in adapters.values():
        adapter("<html><body><p>Warm up extraction.</p></body></html>", "https://warmup.test/")
    inputs = {doc_id: document_html(spec) for doc_id, spec in corpus["documents"].items()}
    rendered = {doc_id: document_html(spec, True) for doc_id, spec in corpus["documents"].items()
                if "rendered_file" in spec}
    report = {
        "schema_version": "1.0", "corpus_version": corpus["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": subprocess.check_output(["git", "-C", str(reader.parent.parent), "rev-parse", "HEAD"], text=True).strip(),
        "manifest_sha256": hashlib.sha256((Path(__file__).parent / "manifest.json").read_bytes()).hexdigest(),
        "reader_sha256": hashlib.sha256(reader.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256((Path(__file__).parent / "evaluate.py").read_bytes()).hexdigest(),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: metadata.version(p) for p in ("trafilatura", "markdownify", "beautifulsoup4", "lxml")},
        "input_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in inputs.items()},
        "rendered_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in rendered.items()},
        "scope": "Local HTML extraction, no requests/model/browser execution. Rendered views replay frozen observations only.",
        "configuration": {"samples": samples, "windows": [12000, None], "trafilatura_format": "xml",
                          "include_comments": False, "include_tables": True, "include_links": True,
                          "deduplicate": False, "policy_or_gold_provided_to_adapters": False},
        "latency_scope": "warm local extraction, excludes imports, fixture loading, scoring, network and model",
        "documents": {}, "comparisons": {},
    }
    for name, adapter in adapters.items():
        records = {}
        for doc_id, html in inputs.items():
            spec = corpus["documents"][doc_id]
            views = {"raw": html}
            if doc_id in rendered:
                views["rendered"] = rendered[doc_id]
            records[doc_id] = {}
            for view, content in views.items():
                record = {"url": spec["url"], "view": view, "http_status": spec.get("http_status", 200),
                          "input_sha256": hashlib.sha256(content.encode()).hexdigest()}
                if spec["access"] == "blocked":
                    record.update({"status": "access_blocked", "blocks": [], "links": [],
                                   "limitations": ["403 body is not report evidence; adapter not called"],
                                   "latency_ms": None, "p95_latency_ms": None})
                else:
                    times = []
                    for _ in range(samples):
                        start = time.perf_counter_ns()
                        extracted = adapter(content, spec["url"])
                        times.append((time.perf_counter_ns() - start) / 1e6)
                    for index, block in enumerate(extracted.blocks):
                        block["id"] = f"{doc_id}:{view}:{name}:b{index + 1}"
                    record.update({"status": "extracted" if extracted.blocks else "empty", "blocks": extracted.blocks,
                                   "links": extracted.links, "limitations": extracted.limitations,
                                   "latency_ms": statistics.median(times),
                                   "p95_latency_ms": sorted(times)[max(0, (95 * len(times) + 99) // 100 - 1)]})
                records[doc_id][view] = record
        report["documents"][name] = records
        for view in ("raw", "rendered"):
            for limit in (12000, None):
                key = f"{name}:{view}:{limit or 'full'}"
                report["comparisons"][key] = {}
                for case in corpus["cases"]:
                    candidate = {"passages": {}, "observed_views": {}}
                    latency = 0
                    for doc_id in case["documents"]:
                        observation = records[doc_id].get(view, records[doc_id]["raw"])
                        if observation["status"] == "access_blocked":
                            continue
                        candidate["passages"][doc_id] = [b["text"] for b in bounded_blocks(observation["blocks"], limit)]
                        candidate["observed_views"][doc_id] = observation["view"]
                        latency += observation["latency_ms"]
                    candidate["telemetry"] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0,
                                              "cost": 0, "currency": "USD", "latency_ms": latency, "samples_per_document": samples,
                                              "latency_scope": "sum of per-document extraction medians; not end-to-end latency"}
                    report["comparisons"][key][case["id"]] = score(case, corpus, candidate)
                    report["comparisons"][key][case["id"]]["extraction_limitations"] = {
                        doc_id: records[doc_id].get(view, records[doc_id]["raw"])["limitations"]
                        for doc_id in case["documents"]
                        if records[doc_id].get(view, records[doc_id]["raw"])["limitations"]
                    }
    return report


def print_summary(report):
    for key, cases in report["comparisons"].items():
        if ":rendered:" in key:
            continue
        found = sum(c["required_passages"] - len(c["missing"]) for c in cases.values())
        total = sum(c["required_passages"] for c in cases.values())
        noise = sum(len(c["annotated_noise_hits"]) for c in cases.values())
        ungrounded = sum(len(c["ungrounded_passage_documents"]) for c in cases.values())
        print(f"{key:39} coverage={found}/{total} noise={noise} grounding_flags={ungrounded}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    result = run(args.reader, args.samples)
    # Generated evaluation artifact, not an edit to source or annotations.
    payload = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode()
    args.output.write_bytes(gzip.compress(payload, mtime=0) if args.output.suffix == ".gz" else payload)
    print_summary(result)
