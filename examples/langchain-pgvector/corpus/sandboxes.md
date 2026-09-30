# Sandboxes for AI agents

A sandbox is a branch with guard rails for autonomous agents. It has a budget: a
maximum number of statements, compute seconds, or wall-clock seconds, after which it
is discarded automatically. Every statement the agent runs is captured in a log.

An agent can run DELETE, ALTER TABLE, or CREATE INDEX inside a sandbox to prove an
answer with real numbers. Changes reach main only through an explicit promote step
after a green verdict, so production is never modified by the experiment itself.
