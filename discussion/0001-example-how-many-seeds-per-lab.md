---
id: 1
title: '[Example] How many seeds per lab?'
type: question
status: resolved
author: agent:worker
waiting_on: none
run_by: carla
labels: []
links:
- lab:1
created: 2026-11-12 10:25
updated: 2026-11-12 11:40
---

**Question:** how many seeds should labs use by default? [[lab:1]] used 5.

This is an EXAMPLE thread showing the format and how a thread moves between people: an agent working
for bob asks bob, who passes the question to carla, carla answers, and carla's agent (whose message started
it) wraps up. `./dash examples --remove` deletes it.

<!-- comment author="bob" date="2026-11-12 10:52" -->
Carla set up the seed policy for the earlier labs, so I'm passing this on.

_waiting on: carla_

<!-- comment author="carla" date="2026-11-12 11:38" -->
5 is fine for cheap labs; use 3 for anything over an hour.

_waiting on: agents_

<!-- comment author="agent:worker" date="2026-11-12 11:40" -->
Noted: 5 seeds by default, 3 for long runs. A real agent would now record this in [[skill:lab]].

_status: open → resolved · waiting on: none_
