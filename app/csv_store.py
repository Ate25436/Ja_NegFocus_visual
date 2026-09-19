import os
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.diff import sentence_diff


JUDGMENT_COLUMNS = ["meaning_preserved", "naturalness", "negation_scope"]
REVIEW_COLUMNS = JUDGMENT_COLUMNS + ["review_comment", "reviewed_at"]
REFERENCE_COLUMNS = [
    "focus_surface", "negation_surface", "focus_class", "arg_types", "toritate",
    "description", "clue", "negation_source_fragment", "negation_replacement",
    "negation_rule_id", "negation_note", "negative_dependent_expressions",
    "affirmative_sentence", "abstract_expression", "abstraction_rationale",
    "except_prefix", "final_expression", "rewrite_rule_id", "rewrite_rationale",
    "span_method", "span_review_status", "span_reason", "negation_decision_type",
    "negation_conversion_status", "negation_review_status", "negation_confidence",
    "negation_forward_rule", "abstraction_rule_id", "abstraction_review_status",
]


class CsvStore:
    def __init__(self, path, backup_count=10, backup_interval=300):
        self.path = Path(path).resolve()
        self.backup_count = max(1, int(backup_count))
        self.backup_interval = max(0, float(backup_interval))
        self.last_backup = None
        self.lock = threading.RLock()
        self.frame = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        required = {"instance_id", "original_sentence", "rewritten_sentence"}
        if not required.issubset(self.frame.columns):
            raise ValueError("CSVに必要な列がありません: " + ", ".join(sorted(required)))
        ids = self.frame["instance_id"]
        if ids.eq("").any() or ids.duplicated().any():
            raise ValueError("instance_idは空欄のない一意な値である必要があります")
        for column in REVIEW_COLUMNS:
            if column not in self.frame:
                self.frame[column] = ""
        for column in JUDGMENT_COLUMNS:
            if not self.frame[column].isin(["", "OK", "NG"]).all():
                raise ValueError(column + "に不正な判定値があります")
        self.indices = {value: index for index, value in enumerate(ids)}
        self.reference_columns = [
            column for column in REFERENCE_COLUMNS
            if column in self.frame and self.frame[column].nunique(dropna=False) > 1
        ]

    def _index(self, instance_id):
        if instance_id not in self.indices:
            raise KeyError(instance_id)
        return self.indices[instance_id]

    def items(self):
        with self.lock:
            return [dict(row, number=index + 1) for index, row in enumerate(
                self.frame[["instance_id"] + JUDGMENT_COLUMNS].to_dict("records")
            )]

    def detail(self, instance_id):
        with self.lock:
            index = self._index(instance_id)
            row = self.frame.iloc[index].to_dict()
            return {
                **{key: row[key] for key in ["instance_id", "original_sentence", "rewritten_sentence"] + REVIEW_COLUMNS},
                "number": index + 1,
                "diff": sentence_diff(row["original_sentence"], row["rewritten_sentence"]),
                "reference": {key: row[key] for key in self.reference_columns},
            }

    def progress(self):
        with self.lock:
            meaning = self.frame["meaning_preserved"]
            naturalness = self.frame["naturalness"]
            scope = self.frame["negation_scope"]
            done = int(self.frame[JUDGMENT_COLUMNS].ne("").all(axis=1).sum())
            return {"total": len(self.frame), "reviewed": done,
                    "unreviewed": len(self.frame) - done,
                    "meaning_ng": int(meaning.eq("NG").sum()),
                    "naturalness_ng": int(naturalness.eq("NG").sum()),
                    "negation_scope_ng": int(scope.eq("NG").sum()),
                    "any_ng": int(self.frame[JUDGMENT_COLUMNS].eq("NG").any(axis=1).sum())}

    def update(self, instance_id, changes):
        with self.lock:
            index = self._index(instance_id)
            if not isinstance(changes, dict) or not changes:
                raise ValueError("更新する項目を指定してください")
            if set(changes) - set(JUDGMENT_COLUMNS + ["review_comment"]):
                raise ValueError("更新できない項目が含まれています")
            for key, value in changes.items():
                if not isinstance(value, str) or (key != "review_comment" and value not in ("", "OK", "NG")):
                    raise ValueError("判定値はOK・NG・空文字、コメントは文字列で指定してください")
            candidate = self.frame.copy(deep=True)
            for key, value in changes.items():
                candidate.at[index, key] = value
            candidate.at[index, "reviewed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self._persist(candidate)
            self.frame = candidate
            return self.detail(instance_id)

    def _persist(self, candidate):
        now = time.monotonic()
        if self.last_backup is None or now - self.last_backup >= self.backup_interval:
            directory = self.path.parent / ".backup"
            directory.mkdir(exist_ok=True)
            name = self.path.stem + datetime.now().strftime("_%Y%m%d_%H%M%S_%f.csv")
            shutil.copy2(self.path, directory / name)
            self.last_backup = now
            for old in sorted(directory.glob(self.path.stem + "_*.csv"), reverse=True)[self.backup_count:]:
                old.unlink()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="",
                                             dir=self.path.parent, suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                candidate.to_csv(output, index=False, lineterminator="\r\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
