"""Offline corpus contract and descriptive metrics; no network/model calls."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def normalize(text):
    return " ".join(text.split())


def load():
    return json.loads((ROOT / "manifest.json").read_text())


def document_html(spec, rendered=False):
    filename = spec.get("rendered_file", spec["file"]) if rendered else spec["file"]
    html = (ROOT / filename).read_text()
    # Frozen deterministic expansion makes the target occur beyond a 12k read.
    prefix = "<section><h2>Background context</h2><p>Deployment notes discuss optional logging, packaging, metrics, service discovery and environment setup. These notes do not define removal semantics.</p></section>"
    return html.replace("<body>", "<body>" + prefix * spec.get("prefix_repeat", 0), 1)


class AnnotationText(HTMLParser):
    """Fixture integrity helper, not a candidate production extractor."""
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)


def validate(corpus):
    assert len({c["id"] for c in corpus["cases"]}) == len(corpus["cases"])
    for case in corpus["cases"]:
        assert case["reservations"] and case["expected"]
        for doc_id, quote, critical in case["required"]:
            assert doc_id in case["documents"] and isinstance(critical, bool)
            spec = corpus["documents"][doc_id]
            parser = AnnotationText()
            parser.feed(document_html(spec, rendered=True))
            # Table annotations explicitly encode row/column associations.
            assert normalize(quote.replace(" | ", " ")) in normalize(" ".join(parser.parts)), (case["id"], quote)
        for doc_id in case["documents"]:
            spec = corpus["documents"][doc_id]
            assert spec["url"].split("/")[2].endswith(".test")
    return True


def score(case, corpus, candidate):
    """candidate.passages is {document_id: [verbatim passage, ...]}.

    Semantic judgments are excluded: metrics describe annotated coverage only.
    Reservations/status require independent review of the supplied explanation.
    """
    passages = candidate.get("passages", {})
    normalized = {key: [normalize(p) for p in value] for key, value in passages.items()}
    found, missing, critical_missing = [], [], []
    relevant_chars = total_chars = 0
    for index, (doc_id, quote, critical) in enumerate(case["required"]):
        label = f"{case['id']}:{index + 1}"
        hit = any(normalize(quote) in p for p in normalized.get(doc_id, []))
        (found if hit else missing).append(label)
        if critical and not hit:
            critical_missing.append(label)
    for doc_id, texts in normalized.items():
        quotes = [normalize(q) for d, q, _ in case["required"] if d == doc_id]
        for text in texts:
            total_chars += len(text)
            intervals = []
            for quote in quotes:
                intervals.extend((m.start(), m.end()) for m in re.finditer(re.escape(quote), text))
            covered_until = 0
            for start, end in sorted(intervals):
                relevant_chars += max(0, end - max(start, covered_until))
                covered_until = max(covered_until, end)
    ungrounded = []
    for doc_id, texts in normalized.items():
        if doc_id not in corpus["documents"]:
            continue
        spec = corpus["documents"][doc_id]
        observations = []
        for rendered in (candidate.get("observed_views", {}).get(doc_id) == "rendered",):
            parser = AnnotationText()
            parser.feed(document_html(spec, rendered=rendered))
            observations.append(normalize(" ".join(parser.parts)))
        for text in texts:
            if not any(text.replace(" | ", " ") in observed for observed in observations):
                ungrounded.append(doc_id)
    noise_hits = []
    for doc_id, texts in normalized.items():
        for noise in corpus["documents"].get(doc_id, {}).get("noise", []):
            if any(normalize(noise) in text for text in texts):
                noise_hits.append({"document": doc_id, "text": noise})
    # Blocked bodies, unknown and unrelated documents cannot be evidence.
    invalid = [d for d in passages if d not in case["documents"] or corpus["documents"][d]["access"] == "blocked"]
    return {
        "required_passages": len(case["required"]),
        "passage_recall": len(found) / len(case["required"]) if case["required"] else None,
        "missing": missing, "critical_omissions": critical_missing,
        "selected_characters": total_chars,
        "annotated_relevance_fraction": relevant_chars / total_chars if total_chars else None,
        "non_gold_fraction": 1 - relevant_chars / total_chars if total_chars else None,
        "annotated_noise_hits": noise_hits, "invalid_evidence_documents": invalid,
        "ungrounded_passage_documents": ungrounded,
        "missing_reservation_labels": sorted(set(case["reservations"]) - set(candidate["reservations"])) if "reservations" in candidate else None,
        "status_label_matches": candidate["status"] == case["expected"] if "status" in candidate else None,
        "semantic_review": "required; matching labels do not establish correctness",
        "telemetry": candidate.get("telemetry", {"calls": None, "input_tokens": None, "output_tokens": None, "cache_tokens": None, "cost": None, "currency": None, "latency_ms": None}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, help="JSON mapping case IDs to candidates")
    args = parser.parse_args()
    corpus = load()
    validate(corpus)
    result = {"version": corpus["version"], "cases": len(corpus["cases"]), "documents": len(corpus["documents"]),
              "input_sha256": {key: hashlib.sha256(document_html(spec).encode()).hexdigest() for key, spec in corpus["documents"].items()},
              "rendered_sha256": {key: hashlib.sha256(document_html(spec, True).encode()).hexdigest() for key, spec in corpus["documents"].items() if "rendered_file" in spec}}
    if args.candidate:
        candidates = json.loads(args.candidate.read_text())
        result["metrics"] = {case["id"]: score(case, corpus, candidates.get(case["id"], {})) for case in corpus["cases"]}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
