"""Reproduce question-context measurements on the frozen offline corpus."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import gzip
import hashlib
from importlib import metadata
import json
from pathlib import Path
import statistics
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"/"fixtures"/"research_corpus"))

from evaluate import load,document_html,score
from bigbrain.research import Passage,Source,Question,ResearchState
from bigbrain.research_context import select,policy_view,review_view
from bigbrain.research_extraction import extract_html,window
from bigbrain.research_acquisition import artifact


def size(view):
    return len(json.dumps(view,ensure_ascii=False).encode())


def phase3_view(state):
    """Recorded phase-3 decision-view transformation for a like-for-like control."""
    view=state.model_dump(mode="json")
    for source in view["sources"]:
        source["observed_link_count"]=len(source.pop("links",[]))
    for passage in view["passages"]:
        passage.pop("review_only",None)
    view["observations"]=[]
    return view


def run(samples):
    corpus=load()
    result={"schema_version":"1.0","corpus_version":corpus["version"],
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "scope":"Offline selection and model-ready evidence JSON; no model, tokenizer, browser or network call",
            "calls":0,"provider_cost_usd":0,"billed_tokens":None,"samples":samples,
            "python":platform.python_version(),"packages":{name:metadata.version(name) for name in ("trafilatura","beautifulsoup4")},
            "harness_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_sha256":{name:hashlib.sha256((ROOT/"bigbrain"/name).read_bytes()).hexdigest()
                             for name in ("research_context.py","research_extraction.py","research.py","research_acquisition.py","research_assessment.py")},
            "manifest_sha256":hashlib.sha256((ROOT/"tests/fixtures/research_corpus/manifest.json").read_bytes()).hexdigest(),
            "cases":{}}
    for case in corpus["cases"]:
        sources=[]
        before,after=[],[]
        original_passages,selected_passages={},{}
        timings=[]
        details={}
        for doc_id in case["documents"]:
            spec=corpus["documents"][doc_id]
            if spec["access"]=="blocked":
                continue
            html=document_html(spec)
            digest=hashlib.sha256(html.encode()).hexdigest()
            prepared=extract_html(html,spec["url"])
            raw=artifact(html.encode(),name="corpus-source.html",media_type="text/html")
            indexed=artifact(json.dumps(prepared,ensure_ascii=False).encode(),name="corpus-blocks.json")
            source=Source(id=doc_id,url=spec["url"],status="read",discovered_by=case["question"],content_sha256=digest,
                          acquisition={"mode":"http","status":"available","engine":prepared["engine"],"raw_artifact":raw,
                                       "blocks_artifact":indexed,"limitations":prepared["limitations"],"title":prepared["title"]})
            old,_=window(prepared["blocks"])
            times=[]
            for _ in range(samples):
                start=time.perf_counter_ns()
                chosen,selection=select(case["question"],prepared["original_blocks"] or prepared["blocks"],digest,
                                        preferred_ids={b["id"] for b in prepared["blocks"]})
                times.append((time.perf_counter_ns()-start)/1e6)
            timings.append(statistics.median(times))
            for items,target in ((old,before),(chosen,after)):
                for i,b in enumerate(items):
                    target.append(Passage(id=f"{doc_id}:p{i}",source_id=doc_id,text=b["text"],kind=b["kind"],
                                          context=b.get("context",[]),observation_sha256=digest,
                                          locator=b["locator"],clipped=b.get("clipped",False)))
            original_passages[doc_id]=[b["text"] for b in old]
            selected_passages[doc_id]=[b["text"] for b in chosen]
            sources.append(source)
            details[doc_id]={"snapshot":digest,"selection":selection}
        common={"objective":case["question"],"questions":[Question(id="q1",text=case["question"],evidence_needed="Direct evidence and its scope")],"sources":sources}
        old_state=ResearchState(**common,passages=before)
        old_bytes=size(phase3_view(old_state))
        for source in sources:
            source.acquisition["selection"]=details[source.id]["selection"]
        new_state=ResearchState(**common,passages=after)
        new_bytes=size(policy_view(new_state))
        review,extras=review_view(new_state)
        result["cases"][case["id"]]={"before":score(case,corpus,{"passages":original_passages}),
                                        "after":score(case,corpus,{"passages":selected_passages}),
                                        "decision_view_bytes_before":old_bytes,"decision_view_bytes_after":new_bytes,
                                        "independent_review_bytes":size(review),"review_extra_passages":len(extras),
                                        "local_selection_ms":sum(timings),"latency_scope":"sum of warm per-document selection medians",
                                        "sources":details,"selected_passages":[p.model_dump(mode="json") for p in after]}
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--samples",type=int,default=25)
    args=parser.parse_args()
    if args.samples<1:
        parser.error("samples must be positive")
    result=run(args.samples)
    payload=(json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode()
    args.output.write_bytes(gzip.compress(payload,mtime=0) if args.output.suffix==".gz" else payload)
    for name,case in result["cases"].items():
        after=case["after"]
        print(f"{name}: gold={after['required_passages']-len(after['missing'])}/{after['required_passages']} chars={case['before']['selected_characters']}->{after['selected_characters']} decision_JSON_bytes={case['decision_view_bytes_before']}->{case['decision_view_bytes_after']}")
