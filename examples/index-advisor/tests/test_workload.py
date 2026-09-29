from unittest.mock import MagicMock

from index_advisor.workload import QUERIES, run_workload


def test_run_workload_runs_every_query_each_round_deterministically():
    a, b = MagicMock(), MagicMock()
    assert run_workload(a, rounds=4, seed=1) == 4 * len(QUERIES)
    run_workload(b, rounds=4, seed=1)
    assert a.execute.call_args_list == b.execute.call_args_list
    sqls = {c.args[0] for c in a.execute.call_args_list}
    assert sqls == {q for q, _ in QUERIES}
    assert all("index_advisor." in q for q, _ in QUERIES)
