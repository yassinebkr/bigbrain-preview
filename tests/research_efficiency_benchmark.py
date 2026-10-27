"""Reproducible acquisition/context baseline using the frozen research corpus.

Exercises the real reader and runtime with scripted decisions and fixture HTTP.
Measures retrieval and orchestration mechanics, not live model reasoning quality.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import inspect
from pathlib import Path
import statistics
import time

from bigbrain.research import Action, Limits, ModelPolicy, ResearchRuntime
from bigbrain.research_acquisition import PageReader, Response, artifact
from bigbrain.research_context import policy_view, select
from bigbrain.research_extraction import extract_html

ROOT = Path(__file__).parent / "fixtures" / "research_corpus"
spec = importlib.util.spec_from_file_location("corpus_evaluate", ROOT / "evaluate.py")
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)


class FixtureFetcher:
    def __init__(self, manifest):
        self.manifest = manifest

    async def fetch(self, url):
        document = next(d for d in self.manifest["documents"].values() if d["url"] == url)
        body = corpus.document_html(document).encode()
        return Response(url, document.get("http_status", 200), body, {"content-type": "text/html"}, "utf-8",
                        artifact(body, name="fixture.html", media_type="text/html"), ())


class FixtureSearch:
    def __init__(self, manifest, case):
        self.manifest, self.case = manifest, case

    async def search(self, query, count):
        return [{"url": self.manifest["documents"][d]["url"], "title": d} for d in self.case["documents"]]


class ScriptedCollection:
    def __init__(self, case, grouped):
        self.case, self.grouped = case, grouped
        self.calls, self.context_bytes = 0, []
        self.request_bytes = []

    async def choose(self, state, remaining):
        self.calls += 1
        self.context_bytes.append(len(json.dumps(policy_view(state), ensure_ascii=False, separators=(',', ':')).encode()))
        base = {"question_id": "q1", "rationale": "Read frozen relevant sources"}
        if not state.sources:
            selected = Action(tool="search", query=state.objective[:500], **base)
        else:
            selected = None
        pending = [s for s in state.sources if s.status == "discovered" and not s.error]
        if selected is None and pending:
            if self.grouped and len(pending) > 1:
                selected = Action(tool="batch", requests=[{**base, "tool": "open", "source_id": s.id} for s in pending[:4]], **base)
            else:
                selected = Action(tool="open", source_id=pending[0].id, **base)
        selected = selected or Action(tool="conclude", **base)
        sizes = self.request_bytes
        class FixtureInference:
            async def complete(self, prompt, **kwargs):
                sizes.append({"prompt": len(prompt.encode()),
                              "protocol": len(json.dumps(kwargs["tool_schema"], ensure_ascii=False).encode())})
                return selected.model_dump_json()
        # Assemble the actual production prompt/schema, but return a scripted
        # action locally. These byte counts are not provider tokens or billing.
        return await ModelPolicy(FixtureInference()).choose(state, {**remaining, "tokens": 200000})


async def run(grouped=False, samples=3):
    manifest = corpus.load()
    corpus.validate(manifest)
    output, selection_comparison = {}, {}
    for case in manifest["cases"]:
        measurements = []
        for _ in range(samples):
            policy = ScriptedCollection(case, grouped)
            async def progress(event):
                pass
            runtime = ResearchRuntime(FixtureSearch(manifest, case), PageReader(fetcher=FixtureFetcher(manifest)),
                policy, progress, limits=Limits(actions=12))
            start = time.perf_counter()
            state = await runtime.run(case["question"])
            elapsed = (time.perf_counter() - start) * 1000
            passages = {d: [p.text for p in state.passages if p.source_id == s.id]
                for s in state.sources for d in case["documents"] if s.url == manifest["documents"][d]["url"]}
            candidate = {"passages": {d: texts for d, texts in passages.items() if texts}}
            metrics = corpus.score(case, manifest, candidate)
            measurements.append(elapsed)
        output[case["id"]] = {"metrics": metrics, "policy_decisions": policy.calls,
            "decision_context_bytes": sum(policy.context_bytes), "largest_context_bytes": max(policy.context_bytes),
            "decision_request_bytes": sum(s["prompt"] + s["protocol"] for s in policy.request_bytes),
            "decision_protocol_bytes": sum(s["protocol"] for s in policy.request_bytes),
            "latency_median_ms": round(statistics.median(measurements), 3),
            "read_attempts": runtime.counts["pages"], "status": state.status,
            "limitations": [s.error for s in state.sources if s.error]}
        selection_comparison[case["id"]] = {}
        for ranking in ("bm25", "contextual"):
            if "ranking" not in inspect.signature(select).parameters and ranking != "bm25":
                selection_comparison[case["id"]][ranking] = {"available": False}
                continue
            # Originals are the same for both rankers. This experiment does not
            # pretend a rendered fixture was acquired by the runtime above.
            selected_by_document = {}
            for doc_id in case["documents"]:
                document = manifest["documents"][doc_id]
                if document["access"] == "blocked":
                    continue
                extracted = extract_html(corpus.document_html(document, rendered=True), document["url"])
                options = {"ranking": ranking} if "ranking" in inspect.signature(select).parameters else {}
                selected, _ = select(case["question"], extracted["original_blocks"], "a"*64,
                    preferred_ids={b["id"] for b in extracted["blocks"]}, **options)
                selected_by_document[doc_id] = [b["text"] for b in selected]
            selection_comparison[case["id"]][ranking] = corpus.score(case, manifest,
                {"passages": selected_by_document, "observed_views": {d: "rendered" for d in selected_by_document}})
    return {"scope": "Offline scripted policy; real extraction/runtime. No network or model; no semantic verdict or billed-token estimate.",
        "corpus_version": manifest["version"], "samples": samples, "grouped": grouped,
        "manifest_sha256": hashlib.sha256((ROOT / "manifest.json").read_bytes()).hexdigest(),
        "source_sha256": {name: hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()
            for name in ("research", "research_context", "research_acquisition")
            for module in [__import__("bigbrain." + name, fromlist=[name])]},
        "gates": {"critical_omissions_must_not_increase": True, "invented_or_blocked_evidence": 0,
                  "independent_multi_page_decisions_must_decrease": True,
                  "live_cost_latency_and_semantics": "not established by this benchmark"},
        "cases": output, "selection_comparison": selection_comparison}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grouped", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(asyncio.run(run(args.grouped)), ensure_ascii=False, indent=2) + "\n")
