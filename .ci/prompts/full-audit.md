You are running a full code quality audit of this repository on a branch created for you. Commit your work on this branch as you go; the pipeline opens the pull request. Never push, never switch branches, never touch the default branch.

Project context: a single user, self hosted personal dashboard that runs on one small home server, maintained by one developer with a zero maintenance goal. Data is tiny (about five thousand finance transactions). Fast API responses and low memory matter more than throughput. Off limits: the public API envelope shape, the SQLite schema, and the appearance and behavior of the UI. This is a quality pass, not a redesign.

Ground rules:
1. Preserve behavior. Do not change what the app does, its public API, its database schema, or its UI unless you are fixing a confirmed bug. Call out every such case in the report.
2. Establish a baseline before touching anything: run the full build, the tests, and the static analysis, and record the results.
3. Work in small, logically grouped commits. After each group rebuild and rerun the tests. Never leave the build broken between steps.
4. Verify, do not assume. A bug counts as fixed only when you reproduced it and added a test that covers it. An optimization counts only when you can state the complexity or a measurement before and after.
5. If you are unsure whether something is intentional, list it under open questions instead of changing it.
6. Do not add dependencies unless there is no reasonable alternative, and justify each one.

Phases, in order:
1. Map the codebase: entry points, modules, data flow, hot paths, and where the tests live.
2. Static analysis: the strict type checker, the linter and formatter, dead code detection, a dependency vulnerability audit, a secret scan, and a manual pass for null handling, async misuse, races, resource leaks, timezone handling, and money precision.
3. Correctness: validate inputs at trust boundaries, make error handling deliberate, check edge cases (empty, large, duplicate, concurrent, timed out), transactions, and concurrency. Fix each confirmed bug with a covering test.
4. Duplication and structure: consolidate repeated logic without over abstracting, remove dead code and stale comments, make naming consistent, prefer early returns.
5. Conciseness: remove verbose code that is not necessary.
6. Performance, in priority order: algorithmic, database and network, memory, then frontend. Give complexity before and after on hot paths.
7. Comments and docs: doc comments on public functions, "why" comments where the code is not obvious, and a README that covers install, configure, run, test, deploy, and every environment variable.
8. Production readiness: security, fail fast configuration, observability, resilience, data and backups, tests, and a reproducible build and CI.

Final verification: the full build, the tests, and the static analysis must pass clean. Compare against the baseline.

Final report (this is the text you return as `report`), with these sections:
1. State before and after
2. Bugs found and fixed, each with file, cause, fix, and test
3. Duplication removed and structural changes
4. Performance changes with complexity or measurements
5. Security and production readiness findings and their status
6. What could not be verified and why
7. Open questions and judgment calls that need a decision
8. Remaining risks and recommended follow up, ranked

Be honest. If something is not production ready, say so plainly.
