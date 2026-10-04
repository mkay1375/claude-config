"""Exercise whether reusable review evidence belongs to the actual request head."""

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/merge-prs/scripts/review_evidence.py"
SPEC = importlib.util.spec_from_file_location("review_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
HEAD = "a" * 40
OTHER = "b" * 40


class ReviewEvidenceTests(unittest.TestCase):
    def check_evidence(self, body="", comments=None, head=HEAD):
        return MODULE.review_evidence({"headRefOid": head, "body": body, "comments": comments or []})

    def test_description_review_can_skip_repeated_review(self):
        evidence = self.check_evidence("## Review\n\nReviewed at " + HEAD + "\nCodex review against origin/main; checks passed")
        self.assertTrue(evidence["reviewed"])
        self.assertEqual(evidence["source"], "description")

    def test_comment_review_can_skip_repeated_review(self):
        evidence = self.check_evidence(comments=[{"body": "Discussion"}, {"body": "Reviewed at " + HEAD + "\nCodex review"}])
        self.assertTrue(evidence["reviewed"])
        self.assertEqual(evidence["index"], 1)

    def test_new_commits_invalidate_both_sources(self):
        evidence = self.check_evidence("Reviewed at " + HEAD, [{"body": "Reviewed at " + HEAD}], head=OTHER)
        self.assertFalse(evidence["reviewed"])

    def test_vague_short_and_quoted_claims_do_not_skip_review(self):
        for body in ["Reviewed; all good", "Reviewed at " + HEAD[:7], "> Reviewed at " + HEAD,
                     "`Reviewed at " + HEAD + "`", "    Reviewed at " + HEAD,
                     "Reviewed at " + HEAD + " extra text"]:
            with self.subTest(body=body):
                self.assertFalse(self.check_evidence(body)["reviewed"])

    def test_fenced_template_is_not_review_evidence(self):
        for fence in ["```", "~~~", "````"]:
            with self.subTest(fence=fence):
                self.assertFalse(self.check_evidence(fence + "text\nReviewed at " + HEAD + "\n" + fence)["reviewed"])
                self.assertTrue(self.check_evidence(fence + "text\nexample\n" + fence + "\n\nReviewed at " + HEAD)["reviewed"])

    def test_lazy_quote_and_list_examples_do_not_certify_review(self):
        for prefix in ["> Example review marker:", "- Example review marker:", "## Review"]:
            with self.subTest(prefix=prefix):
                self.assertFalse(self.check_evidence(prefix + "\nReviewed at " + HEAD)["reviewed"])
        self.assertTrue(self.check_evidence("> Prior discussion\n\nReviewed at " + HEAD)["reviewed"])

    def test_html_examples_and_comments_remain_masked_across_blank_lines(self):
        blocks = [("<pre>", "</pre>"), ("<script>", "</script>"),
                  ("<style>", "</style>"), ("<textarea>", "</textarea>"),
                  ("<!--", "-->"), ("<![CDATA[", "]]>"), ("<?example", "?>")]
        for opening, closing in blocks:
            for gap in ["\n", "\n\n"]:
                with self.subTest(opening=opening, gap=gap):
                    body = opening + gap + "Reviewed at " + HEAD + "\n" + closing
                    self.assertFalse(self.check_evidence(body)["reviewed"])
                    self.assertTrue(self.check_evidence(body + "\n\nReviewed at " + HEAD)["reviewed"])

    def test_generic_html_block_and_declaration_are_not_review_evidence(self):
        for opening, closing in [("<div>", "</div>"), ("<custom-tag>", "</custom-tag>"),
                                 ("<!DOCTYPE", ">")]:
            with self.subTest(opening=opening):
                body = opening + "\nReviewed at " + HEAD + "\n" + closing
                self.assertFalse(self.check_evidence(body)["reviewed"])
                self.assertTrue(self.check_evidence(body + "\n\nReviewed at " + HEAD)["reviewed"])

    def test_nested_or_reopened_raw_html_does_not_certify_review(self):
        for opening in ["<div>\n<pre>", "</pre><pre>", "<!-- closed --><!--"]:
            with self.subTest(opening=opening):
                self.assertFalse(self.check_evidence(opening + "\n\nReviewed at " + HEAD)["reviewed"])

    def test_comment_marker_must_be_first_line(self):
        self.assertFalse(self.check_evidence(comments=[{"body": "Example:\nReviewed at " + HEAD}])["reviewed"])

    def test_gitlab_description_and_notes(self):
        self.assertTrue(MODULE.review_evidence({"sha": HEAD, "description": "Reviewed at " + HEAD, "notes": []})["reviewed"])
        self.assertTrue(MODULE.review_evidence({"sha": HEAD, "description": None, "notes": [{"body": "Reviewed at " + HEAD}]})["reviewed"])

    def test_crlf_markers(self):
        self.assertTrue(self.check_evidence("## Review\r\n\r\nReviewed at " + HEAD + "\r\nVerified.")["reviewed"])

    def test_incomplete_or_invalid_head_cannot_be_certified(self):
        for head in [None, HEAD[:7], "g" * 40]:
            with self.subTest(head=head), self.assertRaises(ValueError):
                self.check_evidence(head=head)


if __name__ == "__main__":
    unittest.main()
