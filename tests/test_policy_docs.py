import unittest
from pathlib import Path

from storekeeper.domain import Intent, Task
from storekeeper.policy_docs import POLICY_DOCS_DIRECTORY, find_policy_context


def make_task(intent: Intent = "refund_request") -> Task:
    return {
        "intent": intent,
        "order_reference": "#1036",
        "requested_action": None,
        "confidence": 0.9,
    }


class FindPolicyContextTests(unittest.TestCase):
    def test_refund_intent_gets_the_returns_document(self) -> None:
        policy_extracts = find_policy_context(make_task("refund_request"))

        self.assertEqual(len(policy_extracts), 1)
        self.assertEqual(policy_extracts[0]["document_name"], "returns-and-refunds.md")
        self.assertIn("30 days", policy_extracts[0]["document_text"])

    def test_policy_question_gets_the_whole_corpus(self) -> None:
        policy_extracts = find_policy_context(make_task("policy_question"))

        document_names = [extract["document_name"] for extract in policy_extracts]
        self.assertEqual(
            document_names,
            [
                "address-changes.md",
                "cancellations.md",
                "returns-and-refunds.md",
                "shipping.md",
                "warranty.md",
            ],
        )

    def test_corpus_numbers_match_the_gate(self) -> None:
        # The gate enforces 30 days / $100; the customer-facing docs must say
        # the same, or replies will contradict decisions.
        returns_text = (POLICY_DOCS_DIRECTORY / "returns-and-refunds.md").read_text(encoding="utf-8")
        self.assertIn("30 days", returns_text)
        self.assertIn("$100", returns_text)

    def test_missing_directory_raises(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "not found"):
            find_policy_context(make_task(), policy_docs_directory=Path("does/not/exist"))


if __name__ == "__main__":
    unittest.main()
