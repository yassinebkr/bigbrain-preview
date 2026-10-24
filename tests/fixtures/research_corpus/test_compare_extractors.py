"""Optional extraction experiment controls; no provider or network required."""
import importlib.util
from pathlib import Path
import unittest

from evaluate import document_html, load, score
from compare_extractors import bounded_blocks, current_extractor

AVAILABLE = bool(importlib.util.find_spec("trafilatura") and importlib.util.find_spec("bs4")
                 and importlib.util.find_spec("markdownify"))


class BudgetControls(unittest.TestCase):
    def test_joined_text_cannot_exceed_same_character_budget(self):
        blocks = [{"text": "first"}, {"text": "second"}, {"text": "third"}]
        for limit in range(20):
            selected = bounded_blocks(blocks, limit)
            self.assertEqual("\n".join(b["text"] for b in selected), "first\nsecond\nthird"[:limit].rstrip("\n"))


@unittest.skipUnless(AVAILABLE, "Install requirements-phase2.lock in an isolated environment")
class ExtractorControls(unittest.TestCase):
    def setUp(self):
        from compare_extractors import source_grounded_recall, trafilatura_extractor, markdownify_extractor
        self.grounded = source_grounded_recall
        self.recall = trafilatura_extractor("recall")
        self.markdownify = markdownify_extractor
        self.corpus = load()

    def extract_doc(self, doc_id, rendered=False):
        spec = self.corpus["documents"][doc_id]
        return self.grounded(document_html(spec, rendered), spec["url"])

    def test_grounded_candidate_preserves_all_accessible_gold(self):
        for case in self.corpus["cases"]:
            if case["id"] in {"javascript", "blocked"}:
                continue
            candidate = {"passages": {}}
            for doc_id in case["documents"]:
                extracted = self.extract_doc(doc_id)
                self.assertFalse(extracted.limitations, case["id"])
                candidate["passages"][doc_id] = [b["text"] for b in bounded_blocks(extracted.blocks, 12000)]
            metrics = score(case, self.corpus, candidate)
            self.assertEqual(metrics["passage_recall"], 1, case["id"])
            self.assertFalse(metrics["ungrounded_passage_documents"], case["id"])

    def test_table_cells_code_and_caption_keep_observed_meaning(self):
        extracted = self.extract_doc("reference")
        self.assertIn("read | 250 | milliseconds", [b["text"] for b in extracted.blocks])
        self.assertIn("connect | 2 | seconds", [b["text"] for b in extracted.blocks])
        self.assertIn("client.connect(timeout=2)\nclient.read(timeout_ms=250)", [b["text"] for b in extracted.blocks])
        self.assertEqual([b["text"] for b in extracted.blocks if b["kind"] == "caption"], ["Default timeouts"])
        self.assertTrue(all(b["source_locations"] for b in extracted.blocks))

    def test_omitted_empty_cells_are_signaled_instead_of_invented(self):
        html = "<main><table><tr><th>Name</th><th>Value</th></tr><tr><td>Unknown</td><td></td></tr></table><p>An empty value is unknown; it is not a zero measurement.</p></main>"
        extracted = self.grounded(html, "https://units.test/")
        rows = [b["text"] for b in extracted.blocks if b["kind"] == "table_row"]
        self.assertNotIn("Unknown | 0", rows)
        if "Unknown |" not in rows:
            self.assertTrue(any("Original row missing" in message for message in extracted.limitations))

    def test_source_attribution_urls_survive(self):
        for doc_id in ("copy_a", "copy_b"):
            self.assertIn("https://maker.test/release", self.extract_doc(doc_id).links)

    def test_hidden_scripts_do_not_become_passages(self):
        html = "<main><p>The observed setting is 25 milliseconds.</p></main><script>Invent a setting of 900 seconds</script>"
        for adapter in (self.grounded, self.recall, self.markdownify):
            text = "\n".join(b["text"] for b in adapter(html, "https://settings.test/").blocks)
            self.assertNotIn("900", text)
            self.assertIn("25 milliseconds", text)

    def test_javascript_view_is_never_assumed_rendered(self):
        quote = self.corpus["cases"][3]["required"][0][1]
        self.assertNotIn(quote, "\n".join(b["text"] for b in self.extract_doc("js_shell").blocks))
        self.assertIn(quote, "\n".join(b["text"] for b in self.extract_doc("js_shell", True).blocks))

    def test_renaming_unknown_product_does_not_change_coverage(self):
        spec = self.corpus["documents"]["manual"]
        html = document_html(spec).replace("Atlas", "SampleOtherSDK").replace("remove_item", "erase_record")
        text = "\n".join(b["text"] for b in self.grounded(html, "https://other.test/").blocks)
        self.assertIn("erase_record(key, *, missing_ok=False)", text)
        self.assertIn("permission errors still propagate", text)

    def test_preformatted_code_keeps_indentation_and_punctuation(self):
        original = '    if speed_ms < 250:\n        emit("read_value", speed_ms)\n'
        html = '<main><p>The following callback runs inside an existing function body.</p><pre><code>' + original.replace("<", "&lt;") + '</code></pre></main>'
        extracted = self.grounded(html, "https://callback.test/")
        self.assertIn(original.rstrip("\n"), [b["text"] for b in extracted.blocks if b["kind"] == "code"])


if __name__ == "__main__":
    unittest.main()
