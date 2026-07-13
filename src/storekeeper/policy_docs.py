"""Store policy documents: the retrieval seam between the corpus and the LLM.

find_policy_context() is the only door to the policy corpus. v1 returns whole
markdown files; the RAG slice replaces this function's internals without
touching any caller. Policy text feeds the answering and drafting LLMs only —
never the policy gate.
"""

from pathlib import Path
from typing import TypedDict

from storekeeper.domain import Intent, Task

# Repo-root policies/ folder, resolved relative to this file so scripts work
# from any working directory.
POLICY_DOCS_DIRECTORY = Path(__file__).resolve().parents[2] / "policies"


class PolicyExtract(TypedDict):
    document_name: str
    document_text: str


# Which documents matter for each intent. None means the whole corpus — it is
# small enough to read whole in v1 (RAG narrows this later).
INTENT_TO_POLICY_DOCUMENT_NAMES: dict[Intent, list[str] | None] = {
    "cancel_order": ["cancellations.md"],
    "refund_request": ["returns-and-refunds.md"],
    "address_change": ["address-changes.md"],
    "policy_question": None,
    "other": None,
}


def find_policy_context(
    task: Task, policy_docs_directory: Path | None = None
) -> list[PolicyExtract]:
    directory = (
        policy_docs_directory if policy_docs_directory is not None else POLICY_DOCS_DIRECTORY
    )
    if not directory.is_dir():
        raise FileNotFoundError(f"Policy corpus directory not found: {directory}")

    wanted_document_names = INTENT_TO_POLICY_DOCUMENT_NAMES[task["intent"]]
    if wanted_document_names is None:
        document_paths = sorted(directory.glob("*.md"))
    else:
        document_paths = [directory / document_name for document_name in wanted_document_names]

    policy_extracts: list[PolicyExtract] = [
        {
            "document_name": document_path.name,
            "document_text": document_path.read_text(encoding="utf-8"),
        }
        for document_path in document_paths
    ]
    if not policy_extracts:
        raise FileNotFoundError(f"No policy documents found in {directory}")
    return policy_extracts


def format_policy_extracts(policy_extracts: list[PolicyExtract]) -> str:
    """Render extracts as one prompt block, each headed by its file name."""
    return "\n\n".join(
        f"[{extract['document_name']}]\n{extract['document_text']}"
        for extract in policy_extracts
    )
