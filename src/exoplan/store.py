"""SQLite store for subjects and classifications, with a Zooniverse-style CSV export.

The export mirrors the column layout of a Zooniverse classification export
(classification_id, user_name, subject_ids, created_at, annotations, metadata),
so the output can be read with the same tools that read Planet Hunters data.
Annotations are stored in the same shape: one entry per task. T0 holds the
marks and T1 holds the potential-planet or noise label.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from exoplan.reviewers.base import Classification
from exoplan.subjects import Subject

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    subject_id TEXT PRIMARY KEY,
    mission TEXT NOT NULL,
    target TEXT NOT NULL,
    time_unit TEXT NOT NULL,
    t_start REAL NOT NULL,
    t_end REAL NOT NULL,
    n_points INTEGER NOT NULL,
    image_path TEXT
);
CREATE TABLE IF NOT EXISTS classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    user_name TEXT NOT NULL,
    label TEXT NOT NULL,
    reason TEXT,
    confidence REAL,
    annotations TEXT NOT NULL,
    metadata TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS classifications_by_subject ON classifications(subject_id);
"""

EXPORT_COLUMNS = ("classification_id", "user_name", "subject_ids", "created_at", "label", "annotations", "metadata")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def add_subject(self, subject: Subject, image_path: str | Path | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO subjects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subject.subject_id,
                subject.mission,
                str(subject.provenance.get("target", "")),
                subject.time_unit,
                subject.start,
                subject.end,
                len(subject),
                None if image_path is None else str(image_path),
            ),
        )

    def add_classification(self, classification: Classification) -> int:
        annotations = [
            {
                "task": "T0",
                "value": [
                    {"t_start": m.t_start, "t_end": m.t_end, "kind": m.kind} for m in classification.marks
                ],
            },
            {"task": "T1", "value": classification.label},
        ]
        metadata = {
            "subject_id": classification.subject_id,
            "confidence": classification.confidence,
            "rationale": classification.rationale,
            "reason": classification.reason,
            **classification.metadata,
        }
        cursor = self.conn.execute(
            "INSERT INTO classifications (subject_id, user_name, label, reason, confidence, annotations, metadata, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                classification.subject_id,
                classification.reviewer_id,
                classification.label,
                classification.reason,
                classification.confidence,
                json.dumps(annotations),
                json.dumps(metadata, default=str),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)

    def classifications(self, subject_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM classifications"
        params: tuple = ()
        if subject_id is not None:
            query += " WHERE subject_id = ?"
            params = (subject_id,)
        return [dict(row) for row in self.conn.execute(query + " ORDER BY classification_id", params)]

    def subject_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0])

    def export_classifications_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for row in self.classifications():
                writer.writerow(
                    {
                        "classification_id": row["classification_id"],
                        "user_name": row["user_name"],
                        "subject_ids": row["subject_id"],
                        "created_at": row["created_at"],
                        "label": row["label"],
                        "annotations": row["annotations"],
                        "metadata": row["metadata"],
                    }
                )
        return path
