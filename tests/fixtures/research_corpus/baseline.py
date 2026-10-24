"""Measure the existing text extractor on frozen inputs, without importing app startup."""
import argparse
import ast
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics
import time

from evaluate import document_html, load, score, validate


def run(reader_path):
    source = reader_path.read_text()
    tree = ast.parse(source)
    extractor = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TextExtractor")
    namespace = {"HTMLParser": HTMLParser}
    exec(compile(ast.Module(body=[extractor], type_ignores=[]), str(reader_path), "exec"), namespace)
    corpus = load()
    validate(corpus)
    results = {}
    for case in corpus["cases"]:
        runs, candidate = [], None
        for _ in range(25):
            start = time.perf_counter_ns()
            passages = {}
            for doc_id in case["documents"]:
                spec = corpus["documents"][doc_id]
                if spec["access"] == "blocked":
                    continue
                parser = namespace["TextExtractor"]()
                parser.feed(document_html(spec))
                passages[doc_id] = ["\n".join(parser.parts)[:12000]]
            runs.append((time.perf_counter_ns() - start) / 1e6)
            candidate = {"passages": passages}
        candidate["telemetry"] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0,
                                  "cost": 0, "currency": "USD", "latency_ms": statistics.median(runs),
                                  "latency_scope": "local fixture loading + extraction; excludes network and model", "samples": 25}
        results[case["id"]] = score(case, corpus, candidate)
    return {"corpus_version": corpus["version"], "reader_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "input_sha256": {key: hashlib.sha256(document_html(spec).encode()).hexdigest() for key, spec in corpus["documents"].items()},
            "scope": "Existing TextExtractor plus first 12000 characters. No focus, browser, policy or semantic review.",
            "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("reader", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.reader), indent=2, ensure_ascii=False))
