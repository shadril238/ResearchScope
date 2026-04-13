"""
Static site data generator.

Writes JSON files into output_dir/ that the frontend consumes.
Also copies them into site/data/ so they are published on GitHub Pages.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.normalization.schema import Author, Lab, Paper, ResearchGap, Topic, University


class SiteGenerator:
    """Write all JSON data files for the static frontend."""

    SITE_DATA_DIR = Path(__file__).parent.parent.parent / "site" / "data"

    # Max papers written to papers.json (served to browsers)
    MAX_FRONTEND_PAPERS = 1000
    # Max papers kept in papers_db.json (accumulation store, not served)
    MAX_DB_PAPERS = 10_000

    def generate(
        self,
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
        output_dir: str = "data",
        labs: list[Lab] | None = None,
        universities: list[University] | None = None,
        editorial: dict | None = None,
    ) -> None:
        os.makedirs(output_dir, exist_ok=True)

        # papers are already sorted by paper_score descending from the pipeline
        frontend_papers = papers[: self.MAX_FRONTEND_PAPERS]
        db_papers       = papers[: self.MAX_DB_PAPERS]

        # Full DB — used by the next pipeline run for accumulation (not browser-served)
        self._write(output_dir, "papers_db.json",   [p.to_dict() for p in db_papers])
        # Frontend slice — slim version, strips heavy creator-content fields
        self._write(output_dir, "papers.json",      [self._slim(p) for p in frontend_papers])
        # Ultra-light search index — title/abstract snippet/authors/venue only
        self._write(output_dir, "search_index.json",[self._search_entry(p) for p in db_papers])

        self._write(output_dir, "authors.json",     [a.to_dict() for a in authors])
        self._write(output_dir, "topics.json",      [t.to_dict() for t in topics])
        self._write(output_dir, "gaps.json",        [g.to_dict() for g in gaps])
        self._write(output_dir, "labs.json",        [l.to_dict() for l in (labs or [])])
        self._write(output_dir, "universities.json",[u.to_dict() for u in (universities or [])])
        self._write(output_dir, "editorial.json",   editorial or {})
        self._write(output_dir, "stats.json",       self._stats(papers, authors, topics, gaps, labs or [], universities or []))

        # Mirror into site/data/ so Pages always has the latest data
        self._mirror_to_site(output_dir)

    # ── Helpers ───────────────────────────────────────────────────────────────

    # Creator-content and internal fields never needed by the browser UI
    _STRIP_FIELDS = {
        "tweet_thread", "linkedin_post", "newsletter_blurb", "video_script_outline",
        "plain_english_explanation", "technical_summary", "score_breakdown",
        "research_gap_signals", "limitations", "future_work",
        "canonical_id", "author_ids", "affiliations_raw", "lab_ids", "university_ids",
        "cluster_id", "prerequisites", "fetched_at",
    }

    @classmethod
    def _slim(cls, paper: Paper) -> dict:
        """Return a browser-friendly dict — drops heavy fields not shown in the UI."""
        d = paper.to_dict()
        for f in cls._STRIP_FIELDS:
            d.pop(f, None)
        return d

    @staticmethod
    def _search_entry(paper: Paper) -> dict:
        """Ultra-light record for the client-side search index."""
        return {
            "id":          paper.id,
            "title":       paper.title,
            "abstract":    (paper.abstract or "")[:300],
            "authors":     paper.authors[:5],
            "venue":       paper.venue,
            "year":        paper.year,
            "paper_score": round(paper.paper_score, 1),
            "paper_url":   paper.paper_url,
            "tags":        paper.tags[:5],
        }

    @staticmethod
    def _write(directory: str, filename: str, data: object) -> None:
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)

    # Files kept in the pipeline output dir but NOT served to the browser
    _DB_ONLY_FILES = {"papers_db.json"}

    def _mirror_to_site(self, output_dir: str) -> None:
        site_data = self.SITE_DATA_DIR
        site_data.mkdir(parents=True, exist_ok=True)
        src = Path(output_dir)
        for json_file in src.glob("*.json"):
            if json_file.name in self._DB_ONLY_FILES:
                # Copy to site/data/ for accumulation (committed to git) but
                # it is never fetched by the frontend JS.
                shutil.copy2(json_file, site_data / json_file.name)
            else:
                shutil.copy2(json_file, site_data / json_file.name)

    @staticmethod
    def _stats(
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
        labs: list[Lab],
        universities: list[University],
    ) -> dict:
        venues: dict[str, int] = {}
        sources: dict[str, int] = {}
        difficulty_dist: dict[str, int] = {}
        type_dist: dict[str, int] = {}
        year_dist: dict[int, int] = {}

        for p in papers:
            venues[p.venue] = venues.get(p.venue, 0) + 1
            sources[p.source] = sources.get(p.source, 0) + 1
            dl = p.difficulty_level or "L2"
            difficulty_dist[dl] = difficulty_dist.get(dl, 0) + 1
            pt = p.paper_type or "methods"
            type_dist[pt] = type_dist.get(pt, 0) + 1
            if p.year:
                year_dist[p.year] = year_dist.get(p.year, 0) + 1

        gap_type_dist: dict[str, int] = {}
        for g in gaps:
            gap_type_dist[g.gap_type] = gap_type_dist.get(g.gap_type, 0) + 1

        return {
            "total_papers":       len(papers),
            "total_authors":      len(authors),
            "total_topics":       len(topics),
            "total_gaps":         len(gaps),
            "total_labs":         len(labs),
            "total_universities": len(universities),
            "papers_by_venue":    venues,
            "papers_by_source":   sources,
            "difficulty_distribution": difficulty_dist,
            "paper_type_distribution": type_dist,
            "papers_by_year":     {str(k): v for k, v in sorted(year_dist.items())},
            "gaps_by_type":       gap_type_dist,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
        }
