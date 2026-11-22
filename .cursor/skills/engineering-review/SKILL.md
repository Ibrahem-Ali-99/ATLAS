---
name: engineering-review
description: Reviews ATLAS changes for correctness, security, domain boundaries, and test evidence. Use when the user asks for an engineering review, a code review, a Day 2–7 implementation review, or explicitly invokes the engineering-review skill.
disable-model-invocation: true
---

# Engineering review

Review the change for defects that affect correctness, security, or operability. Formatting and naming preferences are secondary. Do not implement Day 2–7 features during a review unless the user asked for the fixes.

## Review steps

1. Inspect the actual diff and related code.
2. Verify intended behavior and compatibility.
3. Identify correctness defects and security vulnerabilities.
4. Examine domain boundaries and unnecessary complexity.
5. Review error paths, retries, transactions, and concurrency where relevant.
6. Evaluate types, names, and documentation.
7. Check tests for meaningful coverage and edge cases.
8. Run applicable linting, type checking, tests, and builds.
9. Classify findings as Critical, Major, Minor, or Suggestion.
10. Report precise file locations, reasoning, and recommended fixes.
11. Separate verified defects from potential risks.
12. State any checks that could not be executed.

## ATLAS checks

Read the changed files and the callers they affect. For identity and tenant work, trace the session cookie, CSRF check, and membership lookup. Confirm a client-supplied organization id is not treated as authorization.

Run the checks that match the diff, from the repository root:

```powershell
.\scripts\check.ps1
```

A Python-only diff still needs `uv run ruff check app tests`, `uv run ruff format --check app tests`, `uv run mypy`, and `uv run pytest` in `apps/api`. A web diff still needs `npm run lint`, `npm run build`, and `npm run typecheck` in `apps/web`. Run secret scanning when the diff adds configuration, fixtures, or docs.

Do not report a command as passed unless it was executed in this review and the result was seen.

## Severity

- **Critical**: exploitable auth or tenant bypass, data loss, or a broken release check that hides a failure.
- **Major**: incorrect behavior, a failed transaction boundary, leaked secret material, or a check that does not run on a clean tree.
- **Minor**: a localized defect with a small blast radius.
- **Suggestion**: an optional improvement. Do not block on it.

## Report

```markdown
## Findings

### Critical
- `path:line` — what is wrong, why it matters, and the fix. Verified or potential.

### Major
- None.

### Minor
- None.

### Suggestions
- None.

## Checks
- `command` — passed or failed, with the relevant result.

## Not run
- What was skipped and why.

## Residual risk
- What remains unverified.
```
