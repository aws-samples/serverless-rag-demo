# AIDLC Plugin Design Spec

**Date:** 2026-06-01
**Repo:** Fraser27/aidlc-plugin
**Type:** Claude Code Plugin (skills + hooks + scripts)

## Overview

AIDLC (AI Development Life Cycle) is a Claude Code plugin that enables fully AI-driven development workflows. A single command (`/aidlc-ship`) orchestrates the full cycle: develop, check, review (via independent subagent), fix, and PR creation — with human approval at the final gate.

The plugin is project-agnostic. It auto-detects language, framework, and tooling, then runs the appropriate checks. Per-project overrides are supported via `.aidlc.yml`.

## Architecture

### Components

1. **Detection Engine** — Scans project for marker files, produces a tool profile
2. **Check Runners** — Independent check units with standardized output
3. **Orchestrator** — Drives the full lifecycle (`/aidlc-ship`)
4. **Reviewer** — Independent subagent with no implementation context
5. **Hooks** — Pre/post-commit automation
6. **Config** — `.aidlc.yml` per-project overrides

### Plugin Structure

```
Fraser27/aidlc-plugin/
├── plugin.json
├── README.md
├── LICENSE
├── skills/
│   ├── aidlc-ship.md         # full lifecycle orchestrator
│   ├── aidlc-review.md       # independent reviewer
│   ├── aidlc-fix.md          # fix findings from review
│   ├── aidlc-init.md         # scaffold config for a project
│   └── aidlc-status.md       # show cycle status/history
├── hooks/
│   ├── pre-commit.sh         # format + lint gate
│   └── post-commit.sh        # security scan warning
├── scripts/
│   ├── detect-project.sh     # auto-detect language/framework
│   ├── run-checks.sh         # execute all relevant checks
│   ├── severity-filter.sh    # classify findings
│   └── install-tools.sh      # install missing tools
├── templates/
│   └── aidlc.yml.template    # default config
└── tests/
    ├── test-detection.sh
    └── fixtures/
        ├── python-cdk/
        ├── typescript-next/
        └── go-terraform/
```

## Detection Engine

Scans project root for marker files and produces a tool profile.

### Supported Detection Matrix (v1)

| Language | Formatter | Linter | Security | Types | Deps |
|----------|-----------|--------|----------|-------|------|
| Python | ruff format | ruff check | bandit | mypy | pip-audit |
| TypeScript/JS | prettier | eslint | semgrep | tsc | npm audit |
| Go | gofmt | golangci-lint | gosec | (built-in) | govulncheck |
| Rust | rustfmt | clippy | cargo-audit | (built-in) | cargo-audit |

### IaC Detection

- `cdk.json` -> `cdk synth`
- `*.tf` files -> `terraform validate`
- SAM template -> `sam validate`

### Marker Files

- `requirements.txt` / `pyproject.toml` / `setup.py` -> Python
- `package.json` -> JavaScript/TypeScript (`tsconfig.json` confirms TS)
- `go.mod` -> Go
- `Cargo.toml` -> Rust
- `cdk.json` -> AWS CDK
- `*.tf` -> Terraform

## Check Runners

### Standardized Output

```json
{
  "check": "security",
  "tool": "bandit",
  "status": "findings",
  "findings": [
    {
      "severity": "high",
      "file": "app.py",
      "line": 42,
      "message": "Use of eval() detected",
      "code": "B307"
    }
  ]
}
```

### Severity Classification

- **Critical/High (blocks):** Security vulnerabilities, SQL injection, hardcoded secrets, eval/exec, broken auth, coverage drop >5%
- **Medium (warns):** Performance issues, missing error handling, complex functions, coverage drop 1-5%, deprecated API usage
- **Low (noted):** Style nits not caught by formatter, minor naming suggestions

### Execution Order

1. Format (auto-fixes, stages changes)
2. Lint (auto-fixes what it can, reports rest)
3. Type check (report only)
4. Tests + coverage (run tests, compare coverage delta)
5. Security scan (changed files + full codebase)
6. Dependency audit (check lockfiles for CVEs)
7. IaC validation (synth/validate if applicable)

### Missing Tools

If a tool isn't installed, the check logs a warning and suggests installation but doesn't block. The skill will attempt to install missing tools with user approval.

## Orchestrator (`/aidlc-ship`)

Invoked as: `/aidlc-ship "add retry logic to the query lambda"`

### Flow

```
1. DEVELOP
   - Creates feature branch (aidlc/<short-description>)
   - Implements the requested change (uses TDD if tests exist)
   - Runs checks (format, lint, type) — auto-fixes what it can
   - Commits working code

2. SELF-CHECK
   - Runs full check suite (all 7 checks)
   - If critical/high findings -> goes to FIX step
   - If only medium/low -> continues with warnings noted

3. REVIEW (spawns subagent)
   - Separate agent reads diff with NO implementation context
   - Reviews for: bugs, security, performance, readability, edge cases
   - Produces findings with severity ratings
   - Writes review to .aidlc/reviews/<branch>-<timestamp>.md

4. FIX (if needed)
   - Addresses all high/critical findings from checks + review
   - Logs medium findings as PR comments
   - Re-runs checks to verify fixes
   - Max 3 fix cycles, then escalates to human

5. HUMAN GATE (pauses here)
   - Presents: summary of changes, review findings, check results
   - Human approves or requests changes
   - If approved -> creates PR (or merges if configured)

6. PR CREATION
   - Creates PR with structured body (summary, changes, review notes, check results)
   - Tags medium findings as "known considerations"
```

### Cycle Protection

If the fix->review loop runs 3 times without resolving high findings, it stops and asks the human for guidance instead of looping forever.

## Reviewer (`/aidlc-review`)

### Separation Principle

The reviewer receives ONLY the diff and file context — not the implementation prompt. This prevents "author bias" where the implementer rationalizes shortcuts.

### Review Checklist

1. **Correctness** — Does the code do what it claims? Edge cases? Off-by-one?
2. **Security** — Injection risks, auth gaps, secrets exposure, OWASP top 10
3. **Performance** — N+1 queries, unnecessary loops, missing caching
4. **Error handling** — Unhappy paths covered? Graceful degradation?
5. **Readability** — Could another dev understand this in 6 months?
6. **Testing** — Are tests meaningful? Do they cover the change?
7. **IaC concerns** — Overly permissive IAM? Public resources? Missing encryption?

### Output Format

```markdown
# AIDLC Review — <branch>

## Critical/High (must fix)
- [HIGH] app.py:42 — eval() on user input, command injection risk

## Medium (consider)
- [MED] query_lambda.py:87 — No timeout on HTTP call, could hang Lambda

## Low (noted)
- [LOW] index.py:12 — Variable name `x` is unclear

## Summary
1 high, 1 medium, 1 low finding. Blocking on 1 issue.
```

### Standalone Usage

Can be invoked independently: `/aidlc-review` on any branch/PR.

## Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| pre-commit | Before any commit | Format + lint (auto-fix), block if unfixable errors |
| post-commit | After commit | Run security scan on changed files, warn if findings |

## Configuration (`.aidlc.yml`)

```yaml
version: 1

# Override detected tools
tools:
  formatter: "black"
  linter: "ruff check"
  test: "pytest --cov=. --cov-report=term-missing"
  security: "bandit -r ."
  type_check: "mypy ."
  iac_validate: "cdk synth --quiet"
  dep_audit: "pip-audit"

# Thresholds
coverage:
  min: 80
  fail_on_drop: 5

# Review settings
review:
  threshold: "high"  # block on: high, medium, or all
  max_fix_cycles: 3

# Paths
exclude:
  - "node_modules/"
  - ".venv/"
  - "cdk.out/"

# Custom commands
custom_checks:
  - name: "cdk diff"
    command: "cdk diff 2>&1"
    severity: "medium"

# Branch naming
branch_prefix: "aidlc"
```

### `/aidlc-init` Skill

- Detects the project
- Generates starter `.aidlc.yml` with detected defaults
- Asks user to confirm before writing
- Installs missing tools (with approval)

## Installation

```bash
claude plugins add Fraser27/aidlc-plugin
```

## First Use

```
/aidlc-init
```

## Daily Workflow

```
/aidlc-ship "implement feature X"
```

## Ad-hoc Review

```
/aidlc-review
```

## Testing Strategy

- `tests/test-detection.sh` — Runs detection against fixture projects, verifies correct tool profiles
- `tests/fixtures/` — Minimal project structures for each supported language/framework
- Integration test: run `/aidlc-ship` against a test project with known issues, verify the full cycle completes correctly (requires AWS creds for CDK projects)

## Open Questions (None)

All design decisions have been resolved through brainstorming.
