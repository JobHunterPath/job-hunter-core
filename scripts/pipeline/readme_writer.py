"""README job table rendering for processed matches."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE_START = "<!-- JOBS_TABLE_START -->"
TABLE_END = "<!-- JOBS_TABLE_END -->"
TABLE_HEADER = "| Date | Job | Location | Score | Files |\n|---|---|---|---|---|"


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", text.strip())[:50]


def _parse_existing_rows(table_body: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in table_body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        url_match = re.search(r"\]\((https?://[^)]+)\)", line)
        if url_match:
            rows[url_match.group(1)] = _ensure_location_column(line)
    return rows


def _ensure_location_column(row: str) -> str:
    try:
        left, files_tail = row.rsplit(" | [Files](", 1)
        before_score, score = left.rsplit(" | ", 1)
    except ValueError:
        return row

    before_score = _escape_link_text_pipes(before_score)
    link_end = before_score.rfind(")")
    has_location = link_end != -1 and before_score[link_end + 1 :].strip().startswith("|")
    if not has_location:
        return f"{before_score} | Unknown | {score} | [Files]({files_tail}"
    return f"{before_score} | {score} | [Files]({files_tail}"


def _escape_table_cell(value: object) -> str:
    return str(value or "Unknown").replace("\n", " ").replace("|", r"\|")


def _escape_link_text_pipes(value: str) -> str:
    def _replace(match: re.Match) -> str:
        text = match.group(1).replace("|", r"\|")
        return f"[{text}]({match.group(2)})"

    return re.sub(
        r"\[([^\]]*)\]\((https?://[^)]+)\)",
        _replace,
        value,
    )


def _job_location(job: dict) -> str:
    return _escape_table_cell(job.get("location") or job.get("region") or "Unknown")


def update_readme(matches: list[dict], root: str | Path, today: str) -> None:
    logger.info("[readme] Updating with %s job(s)", len(matches))
    readme_path = Path(root) / "README.md"
    try:
        content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        start_idx = content.find(TABLE_START)
        end_idx = content.find(TABLE_END)
        if start_idx == -1 or end_idx == -1:
            logger.warning("[readme] Markers not found - skipping update")
            return
        table_block = content[start_idx + len(TABLE_START):end_idx]
        existing_rows = _parse_existing_rows(table_block)
        for match in sorted(matches, key=lambda x: x["score"], reverse=True):
            job = match["job"]
            if job["url"] in existing_rows:
                continue
            slug = f"{today}_{slugify(job['company'])}_{slugify(job['title'])}"
            label = _escape_table_cell(f"{job['title']} @ {job['company']}")
            existing_rows[job["url"]] = (
                f"| {today} | [{label}]({job['url']}) | {_job_location(job)}"
                f" | {match['score']} | [Files](jobs/{slug}/) |"
            )
        all_rows = sorted(existing_rows.values(), reverse=True)
        new_table = f"\n{TABLE_HEADER}\n" + "\n".join(all_rows) + "\n"
        updated = (
            content[:start_idx]
            + TABLE_START + new_table + TABLE_END
            + content[end_idx + len(TABLE_END):]
        )
        readme_path.write_text(updated, encoding="utf-8")
        logger.info("[readme] Table now has %s row(s)", len(all_rows))
    except Exception as e:
        logger.error("[readme] Update failed: %s", e)
        raise
