"""Offline Markdown local-link and required-document check; no URL fetching."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "plan",
    "product-spec",
    "architecture",
    "security-model",
    "state-machine",
    "evaluation-methodology",
    "linear-integration",
    "delivery-os-handoff",
    "implementation-status",
    "backlog",
)


def main() -> None:
    errors: list[str] = []
    for name in REQUIRED:
        if not (ROOT / "docs" / f"{name}.md").is_file():
            errors.append(f"missing required document: {name}")
    documents = list((ROOT / "docs").rglob("*.md")) + list(ROOT.glob("*.md"))
    for document in documents:
        content = document.read_text(encoding="utf-8")
        if not content.strip():
            errors.append(f"empty document: {document.relative_to(ROOT)}")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            if link.startswith(("https://", "http://", "mailto:")):
                continue
            local, _, anchor = unquote(link.strip("<>")).partition("#")
            target = (document.parent / local).resolve() if local else document
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"broken local link in {document.relative_to(ROOT)}: {link}")
            elif anchor and target.suffix == ".md":
                headings = re.findall(r"^#+\s+(.+)$", target.read_text(encoding="utf-8"), re.M)
                slugs = {
                    re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
                    for heading in headings
                }
                if anchor not in slugs:
                    errors.append(f"missing anchor: {link}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Checked {len(documents)} Markdown documents; local links valid. "
        "External links not fetched."
    )


if __name__ == "__main__":
    main()
