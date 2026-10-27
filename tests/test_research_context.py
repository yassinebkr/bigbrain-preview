"""Section retrieval, observation binding and independent review context tests."""
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from bigbrain.research import Action, Claim, EvidenceLink, ModelPolicy, PageReader, Passage, Question, ResearchRuntime, ResearchState, Source
from bigbrain.research_acquisition import ReadFailure, artifact
from bigbrain.research_assessment import AssessmentReport, ModelReviewer
from bigbrain.research_context import groups, policy_view, review_view, select
from bigbrain.research_extraction import extract_html


def test_option_retrieval_preserves_dashes_and_case():
    from bigbrain.research_context import rank, words
    sections = [{'blocks':[{'text':text}]} for text in (
        'a ' * 100 + 'ordinary text', '-U --unified: Show context lines.',
        '-a --all: Include ignored items.', '-u --include-extra: Include extra items.')]
    assert 'option:-u' in words('compare -u and -a')
    assert rank('compare -a', sections)[0][0] == 2
    assert rank('compare -u', sections)[0][0] == 3
    assert rank('compare -U', sections)[0][0] == 1


def test_focus_prefers_definition_over_earlier_index_and_keeps_conditions():
    from bigbrain.research_extraction import window
    html = ("<main><table><tr><td>os.unlink()</td><td>Path.unlink()</td></tr></table>"
            + "<p>Unrelated navigation.</p>" * 900
            + '<dl><dt>Path.<span>unlink</span>(missing_ok=False)</dt><dd>'
            '<p>Only FileNotFoundError is ignored when missing_ok is true.</p>'
            '<p>Other errors are propagated.</p></dd></dl></main>')
    parsed = extract_html(html, "https://docs.test/api")
    selected, clipped = window(parsed["original_blocks"], "Path.unlink", limit=1500)
    text = "\n".join(b["text"] for b in selected)
    assert "FileNotFoundError" in text and "Other errors are propagated" in text
    assert "os.unlink()" not in text and clipped
    assert any(b["kind"] == "dt" for b in selected)


def test_compact_passages_share_provenance_without_losing_text_or_ids():
    from bigbrain.research_context import passage_view
    passages = [Passage(id=f"s1:p{i}", source_id="s1", text=f"Observed fragment {i}",
                context=["API reference", "A long shared section heading"], observation_sha256="a"*64)
                for i in range(116)]
    compact = passage_view(passages)
    assert len(compact["passage_contexts"]) == 1
    for original, item in zip(passages, compact["passages"]):
        assert item["id"] == original.id and item["text"] == original.text
        assert compact["passage_contexts"][item["context_ref"]]["observation_sha256"] == original.observation_sha256
    assert len(json.dumps(compact)) < len(json.dumps([p.model_dump() for p in passages])) / 2


def test_bounded_multilingual_decision_preserves_each_read_source():
    from bigbrain.research import Observation
    state = ResearchState(objective='Comparer les limites et les garanties',
        questions=[Question(id='q1', text='Comparer les limites et les garanties', evidence_needed='Preuves directes')])
    for i in range(3):
        sid = f's{i+1}'
        state.sources.append(Source(id=sid, url=f'https://source{i}.test/', status='read', discovered_by='question'))
        focus = 'Concurrency' if i == 0 else 'Garanties'
        state.observations.append(Observation(index=i, action=Action(tool='open', question_id='q1',
            source_id=sid, focus=focus, rationale='Read requested scope'), status='ok', data={}))
        for section in range(4):
            text = ('Concurrency: readers coexist with a writer. One writer only. ' if i == 0 and section == 0
                    else 'Concurrency, comparer les limites et les garanties. ' if i == 0
                    else 'Garanties et limites. ')*90
            state.passages.append(Passage(id=f'{sid}:p{section}', source_id=sid, text=text,
                context=[focus if section == 0 else f'Other {section}'], observation_sha256='a'*64))
    view = policy_view(state, byte_limit=16000)
    assert {c['source_id'] for c in view['passage_contexts']} == {'s1', 's2', 's3'}
    assert any('One writer only.' in p['text'] for p in view['passages'])
    assert len(json.dumps(view, ensure_ascii=False, separators=(',', ':')).encode()) <= 16000
    originals = {p.id:p.text for p in state.passages}
    assert all(p['text'] == originals[p['id']] for p in view['passages'])


@pytest.mark.asyncio
async def test_read_navigation_surfaces_late_sections_and_survives_literal_focus(monkeypatch):
    from tests.test_research_acquisition import network, html_response
    html = '<main>' + ''.join(f'<h2>Site menu {i}</h2><p>Global links and navigation.</p>' for i in range(40))
    html += '<h2>Calibration tolerance</h2><p>Calibration tolerance: 0.25 mm at 20 C.</p>'
    html += '<h2>Calibration limits</h2><p>Other temperatures were never tested.</p></main>'
    calls = network(monkeypatch, lambda request: html_response(html))
    reader = PageReader()
    for focus in (None, 'Calibration tolerance'):
        result = await reader.read('https://public.test/manual', focus=focus, question='calibration tolerance limits')
        navigation = result['acquisition']['navigation']
        assert any('Calibration limits' in item['context'] for item in navigation['catalog'][:3])
        assert navigation['observation_sha256'] == result['sha256']
        assert navigation['omitted_groups'] == 0
        assert len(navigation['catalog']) > 24
    assert len(calls) == 1
    state = ResearchState(objective='Calibration', questions=[], sources=[Source(id='s1', url='https://public.test/manual',
        discovered_by='question', status='read', acquisition=result['acquisition'])])
    compact = policy_view(state)['sources'][0]['navigation']
    assert any(item[1] == 'Calibration limits' for item in compact['sections'])


@pytest.mark.asyncio
async def test_compact_index_preserves_foreign_language_headings_beyond_shortlist(monkeypatch):
    from tests.test_research_acquisition import network, html_response
    html = '<main>' + ''.join(f'<h2>Other topic {i}</h2><p>Background.</p>' for i in range(30))
    html += '<h2>Concurrency</h2><p>Only one writer at a time.</p></main>'
    network(monkeypatch, lambda request: html_response(html))
    result = await PageReader().read('https://public.test/manual', focus='Concurrency',
        question='Combien de rédacteurs peuvent intervenir simultanément ?')
    state = ResearchState(objective='Concurrence', questions=[], sources=[Source(id='s1',
        url='https://public.test/manual', discovered_by='question', status='read', acquisition=result['acquisition'])])
    navigation = policy_view(state)['sources'][0]['navigation']
    assert any(heading == 'Concurrency' for _, heading in navigation['sections'])
    assert navigation['omitted_groups'] == 0
    assert navigation['observation_sha256'] == result['sha256']


@pytest.mark.asyncio
async def test_policy_reserves_review_and_requests_conclusion_before_collection():
    state = state_with_artifact()
    provider = AsyncMock()
    provider.complete.return_value = Action(tool="conclude", question_id="q1", rationale="Conclude from observed evidence").model_dump_json()
    policy = ModelPolicy(provider)
    await policy.choose(state, {"tokens":30000, "review_reserve":16000, "actions":5})
    assert "Collection budget is closing" in provider.complete.call_args.args[0]
    assert policy.last_reserved_tokens <= 14000
    provider.complete.reset_mock()
    with pytest.raises(ValueError, match="allowance"):
        await policy.choose(state, {"tokens":17000, "review_reserve":16000, "actions":5})
    provider.complete.assert_not_awaited()


def blocks():
    result=[]
    for i in range(15):
        result.append({"id":f"h{i}","text":f"Section {i}","kind":"h2","context":[f"Section {i}"],"locator":f"h[{i}]"})
        text = "Ceramic pottery design and colour choices. "*8
        if i==7:
            text="The sprocket calibration tolerance is 0.25 mm. This measurement applies only at 20 °C; other temperatures were not tested."
        result.append({"id":f"p{i}","text":text,"kind":"p","context":[f"Section {i}"],"locator":f"p[{i}]"})
    return result


def state_with_artifact(originals=None):
    originals=originals or blocks()
    ref=artifact(json.dumps({"original_blocks":originals,"blocks":originals}).encode(),name="context-fixture.json")
    sha="a"*64
    selected,selection=select("sprocket calibration tolerance",originals,sha)
    state=ResearchState(objective="sprocket calibration tolerance",questions=[Question(id="q1",text="sprocket calibration tolerance",evidence_needed="Measured value and conditions")],
        sources=[Source(id="s1",url="https://source.test/",discovered_by="query",status="read",content_sha256=sha,
                        acquisition={"blocks_artifact":ref,"selection":selection})],
        passages=[Passage(id=f"s1:p{i}",source_id="s1",text=b["text"],kind=b["kind"],context=b["context"],
                          observation_sha256=sha) for i,b in enumerate(selected)])
    return state


def test_long_review_is_bounded_and_restores_uncited_counterevidence():
    b = blocks()
    for i in range(15,100):
        b.extend([{"id":f"h{i}","kind":"h2","context":[f"Other topic {i}"],"text":f"Other topic {i}","locator":f"h{i}"},
                  {"id":f"p{i}","kind":"p","context":[f"Other topic {i}"],"text":"Unrelated material. "*80,"locator":f"p{i}"}])
    b[-1]["text"] = "A later sprocket calibration audit rejects the tolerance value for production."
    state = state_with_artifact(b)
    chosen = next(p for p in state.passages if "0.25 mm" in p.text)
    state.claims = [Claim(id="c1", question_id="q1", text="The sprocket calibration tolerance is 0.25 mm.",
        basis="Initial reading", evidence=[EvidenceLink(passage_id=chosen.id,relation="supports")])]
    view, extras = review_view(state)
    assert len(json.dumps(view,ensure_ascii=False,separators=(",", ":")).encode()) <= 12000
    assert any("audit rejects" in p["text"] for p in view["passages"])
    assert any("other temperatures were not tested" in p["text"] for p in view["passages"])
    assert view["inspection"]["sources"]["s1"]["omitted_groups"] > 0
    assert chosen.id in {p["id"] for p in view["passages"]}
    assert all(p.observation_sha256 == "a"*64 for p in extras)


@pytest.mark.asyncio
async def test_oversized_required_review_section_stops_before_provider_call():
    b = [{"id":"large","kind":"p","context":["sprocket"],"text":"sprocket "*3000,"locator":"p"}]
    state = state_with_artifact()
    ref = artifact(json.dumps({"original_blocks":b,"blocks":b}).encode(),name="large-review.json")
    state.sources[0].acquisition["blocks_artifact"] = ref
    state.passages = []
    provider = AsyncMock()
    with pytest.raises(ValueError,match="required original section"):
        await ModelReviewer(provider).review(state,{"tokens":60000})
    provider.complete.assert_not_awaited()


def test_review_requires_a_section_from_every_read_source():
    state = state_with_artifact()
    second = state.sources[0].model_copy(deep=True,update={"id":"s2","url":"https://second.test/"})
    state.sources.append(second)
    view, _ = review_view(state)
    assert set(view["inspection"]["sources"]) == {"s1","s2"}
    assert all(s["selected_groups"] for s in view["inspection"]["sources"].values())
    assert {c["source_id"] for c in view["passage_contexts"]} == {"s1","s2"}


def test_review_keeps_evidence_capacity_when_collection_has_a_large_navigation_index():
    state = state_with_artifact()
    state.sources[0].links = ['https://source.test/navigation/' + 'x'*100 + str(i) for i in range(96)]
    state.sources[0].acquisition['navigation'] = {'observation_sha256':'a'*64,
        'catalog':[{'id':f'g{i}', 'context':['UNREAD_NAVIGATION_MARKER '*8], 'characters':500} for i in range(96)]}
    view, _ = review_view(state)
    assert 'UNREAD_NAVIGATION_MARKER' not in json.dumps(view)
    assert 'navigation' not in view['sources'][0]
    assert any('0.25 mm' in passage['text'] for passage in view['passages'])
    assert view['inspection']['sources']['s1']['selected_groups']
    assert len(view['sources'][0]['links']) == 8
    assert view['sources'][0]['links_omitted'] == 88
    assert view['sources'][0]['observed_link_count'] == 96


def test_review_envelope_scales_with_required_evidence_and_retains_every_citation():
    state = ResearchState(objective='Compare the three observed measurements',
        questions=[Question(id='q1', text='Compare measurements', evidence_needed='Values and conditions')])
    for i in range(3):
        sid = f's{i+1}'
        text = f'Measurement {i}: ' + 'Complete experimental conditions. '*125
        original = {'id':'b1', 'text':text, 'kind':'p', 'locator':'p[1]', 'context':['Measurement']}
        ref = artifact(json.dumps({'blocks':[original], 'original_blocks':[original]}).encode(), name='measurement.json')
        state.sources.append(Source(id=sid, url=f'https://source{i}.test/', discovered_by='question',
            status='read', content_sha256='a'*64, acquisition={'blocks_artifact':ref}))
        state.passages.append(Passage(id=sid+':p1', source_id=sid, text=text, kind='p',
            locator='p[1]', context=['Measurement'], observation_sha256='a'*64))
        state.claims.append(Claim(id=f'c{i}', question_id='q1', text=f'Measurement {i} has documented conditions.',
            basis='Observed report', evidence=[EvidenceLink(passage_id=sid+':p1', relation='supports')]))
    view, _ = review_view(state)
    assert 12000 < view['inspection']['byte_limit'] <= 24000
    assert {p['id'] for p in view['passages']} == {p.id for p in state.passages}
    assert all(any(p['text'] == original.text for p in view['passages']) for original in state.passages)


def test_matching_section_keeps_conditions_and_source_order():
    selected,meta=select("sprocket calibration tolerance",blocks(),"a"*64)
    text="\n".join(b["text"] for b in selected)
    assert "0.25 mm" in text and "other temperatures were not tested" in text
    assert "Section 6" in text and "Section 8" in text
    assert len(text)<=6000 and meta["coverage"]=="partial"
    assert all(not b["clipped"] for b in selected)


def test_duplicate_sections_are_collapsed_with_their_scope():
    b=blocks()[14:16]
    unit=groups(b+b,"a"*64)
    assert len(unit)==1 and unit[0]["duplicate_sections"]==1
    assert unit[0]["blocks"]==b


def test_identical_prose_in_distinct_original_blocks_keeps_both_identities():
    first = blocks()[14:16]
    second = [{**block, "id": block["id"] + "-distinct"} for block in first]
    sections = groups(first + second, "a" * 64)
    assert len(sections) == 2
    assert sections[0]["id"] != sections[1]["id"]
    assert sections[0]["blocks"][1]["text"] == sections[1]["blocks"][1]["text"]


def test_ids_change_with_the_observation_but_not_the_question():
    a=groups(blocks(),"a"*64)
    b=groups(blocks(),"b"*64)
    assert a[0]["id"]!=b[0]["id"]
    first=select("calibration",blocks(),"a"*64)[1]
    second=select("pottery",blocks(),"a"*64)[1]
    assert first["catalog"]==second["catalog"]


def test_unknown_terms_request_context_and_offer_an_index():
    selected,meta=select("quantum entanglement",blocks(),"a"*64)
    assert not selected and meta["status"]=="needs_context"
    assert meta["catalog"] and meta["coverage"]=="partial"


def test_oversized_sections_are_reported_instead_of_cutting_a_condition():
    b=[{"id":"b1","text":"sprocket "*1000+"Applies only at 20 °C.","kind":"p","context":[],"locator":"p"}]
    selected,meta=select("sprocket",b,"a"*64)
    assert not selected and meta["status"]=="needs_context" and meta["oversized_group_ids"]


def test_explicit_ids_retrieve_observed_text_without_a_relevance_match():
    sections=groups(blocks(),"a"*64)
    selected,meta=select("unknown",blocks(),"a"*64,requested=[sections[-1]["id"]])
    assert selected and meta["method"]=="explicit-section-ids"
    assert selected[0]["id"]=="h14"
    with pytest.raises(ValueError,match="observation"):
        select("query",blocks(),"a"*64,requested=["fabricated"])


def test_curated_blocks_keep_an_explicit_path_to_the_full_original_section():
    b=blocks()[14:16]
    b.append({"id":"notice","text":"A separate source qualification.","kind":"text","context":b[0]["context"],"locator":"aside"})
    selected,meta=select("calibration",b,"a"*64,preferred_ids={"h7","p7"})
    assert len(selected)==2 and meta["coverage"]=="partial" and meta["partial_group_ids"]
    full,_=select("calibration",b,"a"*64,requested=meta["partial_group_ids"],preferred_ids={"h7","p7"})
    assert any(v["id"]=="notice" for v in full)


def test_unicode_questions_and_unknown_identifiers_use_the_same_ranker():
    b=blocks()
    b[15]={**b[15],"text":"La durée de l’étalonnage ZetaNode est de 15 minutes. Mesure limitée au prototype."}
    for query in ("durée étalonnage", "ZetaNode"):
        selected,_=select(query,b,"a"*64)
        assert any("Mesure limitée au prototype" in v["text"] for v in selected)


def test_independent_review_restores_a_distant_reservation():
    b=blocks()
    # Cross-reference phrasing has no query-term overlap: the independent review
    # must still see it even when lexical selection cannot identify its role.
    b[-1]={**b[-1],"text":"A later audit found this procedure unsafe; the reported value must not be used for production."}
    state=state_with_artifact(b)
    decision=policy_view(state)
    assert not any("later audit" in p["text"] for p in decision["passages"])
    view,extras=review_view(state)
    assert any("later audit" in p["text"] for p in view["passages"])
    assert all(p.review_only for p in extras)
    assert len(state.passages)==len(decision["passages"])


def test_missing_original_evidence_blocks_cannot_be_silently_ignored():
    state=state_with_artifact()
    state.sources[0].acquisition["blocks_artifact"]["sha256"]="0"*64
    with pytest.raises(ValueError,match="unavailable"):
        review_view(state)


def test_unwrapped_source_reservations_enter_the_original_index():
    pytest.importorskip("trafilatura")
    html="<!doctype html><main><h1>Measurements</h1><p>The stated value is 0.25 mm.</p></main><aside>Later withdrawn after an audit.</aside><!-- Unpublished fake measurement 900 -->"
    indexed=extract_html(html,"https://source.test/")
    text="\n".join(b["text"] for b in indexed["original_blocks"])
    assert "Later withdrawn after an audit" in text
    assert "900" not in text


def test_review_supplements_stay_out_of_decision_context_until_cited():
    state=state_with_artifact()
    _,extras=review_view(state)
    state.passages.extend(extras)
    chosen=extras[-1]
    assert chosen.id not in {p["id"] for p in policy_view(state)["passages"]}
    state.claims=[Claim(id="c1",question_id="q1",text="Provisional",basis="Inspect evidence",evidence=[EvidenceLink(passage_id=chosen.id,relation="context")])]
    assert chosen.id in {p["id"] for p in policy_view(state)["passages"]}


@pytest.mark.asyncio
async def test_review_reserves_output_and_stops_before_provider_io_if_too_large():
    state=state_with_artifact()
    provider=AsyncMock()
    with pytest.raises(ValueError,match="allowance"):
        await ModelReviewer(provider).review(state,{"tokens":1000})
    provider.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_review_prompt_contains_the_original_counterevidence():
    b=blocks()
    b[-1]={**b[-1],"text":"Original distant counterevidence must be inspected before concluding."}
    state=state_with_artifact(b)
    provider=AsyncMock()
    provider.complete.return_value=AssessmentReport(sources=[],claims=[]).model_dump_json()
    reviewer=ModelReviewer(provider)
    await reviewer.review(state,{"tokens":60000})
    assert "Original distant counterevidence" in provider.complete.call_args.args[0]
    assert reviewer.observed_passages


def test_section_actions_are_bound_to_an_observation_identity():
    kwargs={"tool":"open","question_id":"q1","rationale":"Read omitted scope","source_id":"s1","group_ids":["g1"]}
    with pytest.raises(ValidationError):
        Action(**kwargs)
    assert Action(**kwargs,observation_sha256="a"*64).group_ids==["g1"]


@pytest.mark.asyncio
async def test_policy_prompt_preserves_required_passages_without_artifact_payloads():
    state=state_with_artifact()
    state.sources[0].acquisition["requests"]=[{"body":"internal-request-payload"}]
    state.sources[0].acquisition["title"]="Observed reference version 3"
    state.sources[0].acquisition["selection"].update(catalog_truncated=True,omitted_group_count=80)
    state.sources[0].acquisition["blocks_artifact"]["metadata"]={"private_note":"artifact-internal-marker"}
    provider=AsyncMock()
    provider.complete.return_value=Action(tool="clarify",question_id="q1",rationale="Resolve scope",clarification="Which version?").model_dump_json()
    await ModelPolicy(provider).choose(state,{"tokens":60000})
    prompt=provider.complete.call_args.args[0]
    assert "0.25 mm" in prompt and "other temperatures were not tested" in prompt
    assert "artifact-internal-marker" not in prompt and "internal-request-payload" not in prompt
    assert "Observed reference version 3" in prompt
    assert policy_view(state)["sources"][0]["selection"]["catalog_truncated"] is True
    assert policy_view(state)["sources"][0]["selection"]["omitted_group_count"]==80


@pytest.mark.asyncio
async def test_reader_refinement_uses_cached_sections_and_rejects_a_stale_identity():
    pytest.importorskip("trafilatura")
    from bigbrain.research_acquisition import Response
    body=("<main>"+"".join(f"<h2>Part {i}</h2><p>Ceramic pottery design for profile {i}: "+
                          " ".join(f"code{i}v{n}" for n in range(80))+"</p>" for i in range(12))+"</main>").encode()
    ref=artifact(body,name="sections.html",media_type="text/html")
    response=Response("https://source.test/",200,body,{"content-type":"text/html"},"utf-8",ref,())
    fetcher=AsyncMock()
    fetcher.fetch.return_value=response
    reader=PageReader(fetcher=fetcher)
    with pytest.raises(ReadFailure) as failed:
        await reader.read(response.url,question="quantum entanglement")
    assert failed.value.status=="needs_context"
    section=failed.value.record["selection"]["catalog"][0]["id"]
    page=await reader.read(response.url,group_ids=[section],observation_sha256=ref["sha256"])
    assert page["acquisition"]["cache_hit"] and "Ceramic pottery" in page["text"]
    with pytest.raises(ReadFailure) as stale:
        await reader.read(response.url,group_ids=[section],observation_sha256="0"*64)
    assert stale.value.status=="snapshot_changed"
    fetcher.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_registers_supplementary_review_quotes_and_reuses_the_verdict():
    from bigbrain.research_assessment import CitationAssessment,ClaimAssessment,SourceAssessment
    b=blocks()
    b[-1]={**b[-1],"text":"The later audit rejects this value for production use."}
    fixture=state_with_artifact(b)
    selected,selection=select(fixture.objective,b,"a"*64)
    reader,search,progress=AsyncMock(),AsyncMock(),AsyncMock()
    search.search.return_value=[{"url":"https://source.test/"}]
    reader.read.return_value={"url":"https://source.test/","sha256":"a"*64,"text":"\n".join(p["text"] for p in selected),
                              "blocks":selected,"acquisition":fixture.sources[0].acquisition}
    class Steps:
        async def choose(self,state,remaining):
            shared={"question_id":"q1","rationale":"Inspect direct observations and scope"}
            n=len(state.observations)
            if n==0:
                return Action(tool="search",query=fixture.objective,**shared)
            if n==1:
                return Action(tool="open",source_id="s1",**shared)
            if n==2:
                found=next(p for p in state.passages if "0.25 mm" in p.text)
                claim=Claim(id="c1",question_id="q1",text="The stated tolerance can be used in production.",basis="Provisional reading",
                            evidence=[EvidenceLink(passage_id=found.id,relation="supports")])
                return Action(tool="assess",claims=[claim],**shared)
            return Action(tool="conclude",**shared)
    provider=AsyncMock()
    async def complete(prompt,**kwargs):
        view=json.loads(prompt.split("\n",1)[1])["evidence"]
        support=next(p for p in view["passages"] if "0.25 mm" in p["text"])
        counter=next(p for p in view["passages"] if "later audit rejects" in p["text"])
        report=AssessmentReport(sources=[SourceAssessment(source_id="s1",kind="primary",nature="documentation",suitability="limited",
                 basis="Internally contested report",provenance_passage_id=support["id"],provenance_quote=support["text"])],
            claims=[ClaimAssessment(claim_id="c1",relevant=True,rationale="A later audit disputes the value",considered_source_ids=["s1"],
                 citations=[CitationAssessment(passage_id=support["id"],quote=support["text"],relation="supports",explanation="Initial value"),
                            CitationAssessment(passage_id=counter["id"],quote=counter["text"],relation="contradicts",explanation="Later restriction")])])
        return report.model_dump_json()
    provider.complete.side_effect=complete
    state=await ResearchRuntime(search,reader,Steps(),progress,reviewer=ModelReviewer(provider)).run(fixture.objective)
    # A valid contested claim review is retained, but is not a declaration that
    # the complete question has been answered (the legacy report has no coverage).
    assert state.status=="partial",state.assessment_error
    assert state.answer_status == "partial"
    assert state.claims[0].status=="contested"
    assert "s1" in state.assessments[0]["inspection"]["sources"]
    registered={p.id for p in state.passages}
    assert all(e.passage_id in registered for e in state.claims[0].evidence)
    assert any(p.review_only and "later audit rejects" in p.text for p in state.passages)
    assert any(call.args[0]["stage"]=="research_review_evidence" for call in progress.call_args_list)
    provider.complete.assert_awaited_once()
