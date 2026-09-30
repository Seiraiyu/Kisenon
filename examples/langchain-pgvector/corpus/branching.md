# Database branching

A Kisenon branch is a copy-on-write fork of a Postgres database. Creating one takes
a few seconds no matter how large the parent is, because no data is copied up
front: the fork shares storage pages with its parent until either side writes.

Branches are cheap enough to create per task: one per pull request, one per test run,
one per AI agent attempt. When the task is finished the branch is deleted and its
compute endpoint goes away with it. `keon branches create --parent main` forks from
the current state of main; `--parent-lsn` forks from a point in the past.
