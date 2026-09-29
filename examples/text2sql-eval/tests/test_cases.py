from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from text2sql_eval.cases import Case, CaseFileError, Outcome, load_cases, normalize_row, score

EXAMPLE_DIR = Path(__file__).resolve().parents[1]


def _outcome(rows=None, rowcount=None, error=None, status="SELECT 1"):
    return Outcome(sql="x", rows=rows, rowcount=rowcount, status=status, error=error, duration_ms=1)


def test_load_shipped_cases():
    cases = load_cases(EXAMPLE_DIR / "cases.yaml")
    assert len(cases) == 9
    assert cases[0] == Case(id="active-users", question="How many active users are there?",
                            expected_rows=[[750]])
    assert cases[6].expected_rowcount == 100


@pytest.mark.parametrize("body, msg", [
    ("cases: []", "non-empty"),
    ("cases:\n  - question: q\n    expected_rows: [[1]]", "needs `id` and `question`"),
    ("cases:\n  - id: a\n    question: q", "exactly one of"),
    ("cases:\n  - id: a\n    question: q\n    expected_rows: [[1]]\n    expected_rowcount: 1",
     "exactly one of"),
    ("cases:\n  - {id: a, question: q, expected_rowcount: 1}\n"
     "  - {id: a, question: q, expected_rowcount: 1}", "duplicate"),
])
def test_load_rejects_bad_files(tmp_path, body, msg):
    p = tmp_path / "c.yaml"
    p.write_text(body)
    with pytest.raises(CaseFileError, match=msg):
        load_cases(p)


def test_normalize_row():
    assert normalize_row((Decimal("41114000"), Decimal("2.50"), date(2026, 1, 2), "x", None)) == (
        41114000, 2.5, "2026-01-02", "x", None,
    )


def test_score_exact_and_set():
    case = Case(id="c", question="q", expected_rows=[["BR", 1], ["DE", 2]])
    assert score(case, _outcome(rows=[("BR", 1), ("DE", 2)])) == ("exact", "exact match")
    assert score(case, _outcome(rows=[("DE", 2), ("BR", 1)])) == ("set", "same rows, other order")
    assert score(case, _outcome(rows=[("DE", 2)])) == (None, "rows differ")


def test_score_ordered_requires_exact():
    case = Case(id="c", question="q", expected_rows=[[1], [2]], ordered=True)
    assert score(case, _outcome(rows=[(2,), (1,)])) == (None, "rows differ (order matters)")


def test_score_rowcount():
    case = Case(id="c", question="q", expected_rowcount=100)
    assert score(case, _outcome(rowcount=100, status="DELETE 100")) == ("rowcount", "rowcount 100")
    assert score(case, _outcome(rowcount=7, status="DELETE 7")) == (None, "rowcount 7, expected 100")
    assert score(case, _outcome(rows=[(1,)])) == (None, "expected a write, got a result set")


def test_score_error_and_wrong_kind():
    assert score(Case(id="c", question="q", expected_rows=[[1]]), _outcome(error="boom")) == (
        None, "error: boom",
    )
    assert score(Case(id="c", question="q", expected_rows=[[1]]),
                 _outcome(rowcount=3, status="UPDATE 3")) == (None, "expected rows, got a write")
