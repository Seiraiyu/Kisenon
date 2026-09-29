"""pytest plugin: fork a pre-seeded fixture branch once per session, reset it per test.

Registered via the `pytest11` entry point, so installing this package is enough.

  --kisenon-fixture NAME   fixture branch to fork: fixture-NAME (default: small)
  --kisenon-keep           keep the session fork for debugging

Fixtures:
  kisenon_fork   session: the forked Branch (deleted at session end)
  kisenon_db     function: a connection URL; the fork is reset after each test
"""
from __future__ import annotations

import os
import uuid

import pytest

from seed_snapshots import keon


def pytest_addoption(parser):
    group = parser.getgroup("kisenon")
    group.addoption("--kisenon-fixture", default="small",
                    help="fork branch fixture-NAME per session (default: small)")
    group.addoption("--kisenon-keep", action="store_true",
                    help="keep the session fork instead of deleting it")


@pytest.fixture(scope="session")
def kisenon_project() -> str:
    project = os.environ.get("KISENON_PROJECT_ID")
    if not project:
        pytest.exit("KISENON_PROJECT_ID is not set (see README: Setup)", returncode=2)
    return project


@pytest.fixture(scope="session")
def kisenon_fork(request, kisenon_project):
    fixture = request.config.getoption("kisenon_fixture")
    parent_id = keon.find_branch_id(project=kisenon_project, name=f"fixture-{fixture}")
    fork = keon.create_branch(project=kisenon_project,
                              name=f"seed-snapshots-{uuid.uuid4().hex[:8]}",
                              parent_id=parent_id)
    try:
        yield fork
    finally:
        if request.config.getoption("kisenon_keep"):
            print(f"\nkept {fork.name}: keon branches delete --cascade {fork.id}")
        else:
            keon.delete_branch(branch_id=fork.id)


@pytest.fixture
def kisenon_db(kisenon_project, kisenon_fork):
    # URL re-fetched per test in case a reset moves the endpoint.
    yield keon.get_branch_url(project=kisenon_project, branch=kisenon_fork.name)
    # ponytail: resets after every test, including the last one (one wasted reset
    # per session); track dirtiness if that ever matters.
    keon.reset_branch(branch_id=kisenon_fork.id)
