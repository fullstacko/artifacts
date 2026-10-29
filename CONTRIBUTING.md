# Contributing

See the [README](README.md) for what this repository contains. The artifacts
back up published pieces, so the repository is maintained by Fullstacko rather
than as a community project.

## Issues

Issues are welcome and we read every one. Please open one for:

- Code that doesn't run, or no longer runs against the versions stated in the
  artifact's README (for example, a new SDK or spec release).
- Behavior that contradicts what the article or research piece describes.
- Incorrect, unclear or outdated documentation.
- Security problems in the sample code. The samples are educational sketches,
  not production code, and their README says so; a missing production feature
  (persistence, rate limiting, audit logging) is expected rather than a bug.

When reporting a problem, include the artifact folder, the command you ran,
the Python and key dependency versions, and the full output or error.

## Pull requests

Pull requests won't be merged. We keep the artifacts in lockstep with the
published articles and research, and we maintain them ourselves so we can
stand behind everything in the repository. Describe the fix or suggestion in
an issue instead, and we'll apply it if it's right.

## Notes for maintainers

- Each artifact folder has its own `README.md` with setup, a file table and
  run instructions. Keep it current when files change.
- Record the versions an artifact was verified against (language, SDK, spec
  revision) in its README, and update them when re-verified.
- Python artifacts should pass `ruff check`, `ruff format` and
  `mypy --strict`.
- Prefer [uv](https://docs.astral.sh/uv/) for Python code samples (environments,
  dependencies and run instructions), and [pnpm](https://pnpm.io/) for
  JavaScript/TypeScript samples.
