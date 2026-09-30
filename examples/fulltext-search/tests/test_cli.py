from unittest.mock import MagicMock

from fulltext_search import cli


def _result(rows):
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def test_search_uses_fts_when_it_matches():
    conn = MagicMock()
    conn.execute.side_effect = [_result([(3, "Choosing the right index", 0.5, "[GIN] handles")])]
    mode, hits = cli.search(conn, "gin index")
    assert mode == "fts"
    assert hits == [{"id": 3, "title": "Choosing the right index", "rank": 0.5,
                     "snippet": "[GIN] handles"}]
    assert conn.execute.call_count == 1
    assert "websearch_to_tsquery" in conn.execute.call_args.args[0]


def test_search_falls_back_to_trigrams_on_zero_hits():
    conn = MagicMock()
    conn.execute.side_effect = [
        _result([]),
        MagicMock(),
        _result([(2, "Vacuum and table bloat", 0.6667, "Updates and deletes")]),
    ]
    mode, hits = cli.search(conn, "vacum")
    assert mode == "fuzzy"
    assert hits[0]["title"] == "Vacuum and table bloat"
    sqls = [c.args[0] for c in conn.execute.call_args_list]
    assert sqls[1] == "SET pg_trgm.word_similarity_threshold = 0.3"
    assert "<%" in sqls[2]


def test_load_inserts_every_article():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    assert cli.load(conn) == 20
    assert "CREATE SCHEMA fulltext_search" in conn.execute.call_args_list[0].args[0]
    assert len(cur.executemany.call_args.args[1]) == 20


def test_missing_database_url_exits_2(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main(["search", "x"]) == 2
