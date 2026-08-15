#!/usr/bin/env python3
"""Turn Google Search Console CSV exports into a ClientCellar SEO action list."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GscRow:
    query: str
    page: str
    clicks: float
    impressions: float
    ctr: float
    position: float


def normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def first_value(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if row.get(key):
            return row[key].strip()
    return ""


def parse_number(value: str) -> float:
    cleaned = (value or "").strip().replace(",", "").replace("%", "")
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_ctr(value: str) -> float:
    cleaned = (value or "").strip()
    if not cleaned:
        return 0.0
    number = parse_number(cleaned)
    if "%" in cleaned:
        return number / 100
    if number > 1:
        return number / 100
    return number


def load_gsc_rows(path: Path) -> list[GscRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        rows = []
        for raw_row in reader:
            row = {normalise_header(key): value for key, value in raw_row.items() if key}
            rows.append(
                GscRow(
                    query=first_value(row, ("query", "queries", "top_queries", "search_query")),
                    page=first_value(row, ("page", "pages", "top_pages", "url", "landing_page")),
                    clicks=parse_number(first_value(row, ("clicks", "click"))),
                    impressions=parse_number(first_value(row, ("impressions", "impression"))),
                    ctr=parse_ctr(first_value(row, ("ctr", "click_through_rate"))),
                    position=parse_number(first_value(row, ("position", "average_position", "avg_position"))),
                )
            )
    return rows


def row_label(row: GscRow) -> str:
    parts = []
    if row.query:
        parts.append(f"query: {row.query}")
    if row.page:
        parts.append(f"page: {row.page}")
    return " | ".join(parts) or "unlabelled row"


def classify_row(row: GscRow) -> tuple[str, str, int]:
    impressions = row.impressions
    ctr = row.ctr
    position = row.position

    if impressions >= 100 and ctr < 0.02 and 1 <= position <= 12:
        return (
            "Improve title/meta and first-screen relevance",
            "High impressions with weak CTR in a reachable position.",
            1,
        )
    if impressions >= 80 and 8 < position <= 20:
        return (
            "Strengthen existing page or create a better-matched section",
            "Striking-distance query/page that may move with better coverage and internal links.",
            2,
        )
    if row.clicks >= 5 and position <= 10:
        return (
            "Add monetisation and planner CTAs",
            "This already gets clicks; make sure it routes to planners, Premium and supplier opportunities.",
            3,
        )
    if impressions >= 50 and not row.page:
        return (
            "Map query to an existing page or content gap",
            "Query export has demand but no page context in this CSV.",
            4,
        )
    return (
        "Monitor",
        "Lower immediate priority until impressions, clicks or position improve.",
        9,
    )


def priority_rows(rows: list[GscRow], limit: int) -> list[tuple[GscRow, str, str, int]]:
    classified = [(row, *classify_row(row)) for row in rows]
    return sorted(
        classified,
        key=lambda item: (item[3], -item[0].impressions, item[0].position or 100),
    )[:limit]


def format_markdown(rows: list[GscRow], limit: int) -> str:
    output = [
        "# ClientCellar GSC action list",
        "",
        f"Rows analysed: {len(rows)}",
        "",
        "| Priority | Query / page | Clicks | Impressions | CTR | Position | Action | Why |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row, action, reason, priority in priority_rows(rows, limit):
        output.append(
            "| {priority} | {label} | {clicks:g} | {impressions:g} | {ctr:.2%} | {position:g} | {action} | {reason} |".format(
                priority=priority,
                label=row_label(row).replace("|", "/"),
                clicks=row.clicks,
                impressions=row.impressions,
                ctr=row.ctr,
                position=row.position,
                action=action,
                reason=reason,
            )
        )
    output.extend(
        [
            "",
            "## How to use this",
            "",
            "- Priority 1: rewrite title/meta, intro and above-the-fold CTA first.",
            "- Priority 2: improve page depth, add sections that match the query, and strengthen internal links.",
            "- Priority 3: keep rankings stable and add better planner, Premium and supplier CTAs.",
            "- Priority 4: map the query to an existing page or create a page only if no good match exists.",
            "- Priority 9: monitor for now.",
        ]
    )
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse a Google Search Console CSV export.")
    parser.add_argument("csv_file", type=Path, help="Path to a Search Console CSV export.")
    parser.add_argument("--limit", type=int, default=25, help="Number of action rows to show.")
    args = parser.parse_args()

    rows = load_gsc_rows(args.csv_file)
    print(format_markdown(rows, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
