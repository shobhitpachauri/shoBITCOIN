"""Update the README daily progress log with completed pipeline results."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
NEXT_UPDATE_MARKER = "### Next update"


def record_progress(stage: str, completed: list[str], result: str, next_step: str) -> None:
    """Add one dated stage result before the README's Next update template."""
    readme = README_PATH.read_text(encoding="utf-8")
    if NEXT_UPDATE_MARKER not in readme:
        raise RuntimeError(f"README is missing the {NEXT_UPDATE_MARKER!r} marker.")

    date = datetime.now(UTC).date().isoformat()
    lines = [f"### {date} — {stage}", ""]
    lines.extend(f"- {item}" for item in completed)
    lines.extend([f"- Result: {result}", f"- Next step: {next_step}", "", NEXT_UPDATE_MARKER])
    updated = readme.replace(NEXT_UPDATE_MARKER, "\n".join(lines), 1)
    README_PATH.write_text(updated, encoding="utf-8")
