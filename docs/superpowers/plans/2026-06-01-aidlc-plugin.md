# AIDLC Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `Fraser27/aidlc-plugin` Claude Code plugin that provides a fully AI-driven development lifecycle via `/aidlc-ship`.

**Architecture:** A Claude Code plugin with skills (markdown instruction files), shell scripts (detection, checks, severity filtering), hooks (pre/post-commit), and a config template. The plugin auto-detects project language/framework and runs appropriate checks.

**Tech Stack:** Bash scripts, Claude Code plugin manifest (JSON), Markdown skills, YAML config

---

## File Structure

```
aidlc-plugin/
├── plugin.json                    # Plugin manifest — declares skills and hooks
├── README.md                      # Installation and usage docs
├── LICENSE                        # MIT license
├── skills/
│   ├── aidlc-ship.md             # Orchestrator skill — full lifecycle
│   ├── aidlc-review.md           # Independent reviewer skill
│   ├── aidlc-fix.md              # Fix reviewer findings skill
│   ├── aidlc-init.md             # Project scaffold/config skill
│   └── aidlc-status.md           # Show cycle status
├── hooks/
│   ├── pre-commit.sh             # Format + lint on commit
│   └── post-commit.sh            # Security scan after commit
├── scripts/
│   ├── detect-project.sh         # Auto-detect language/framework/tools
│   ├── run-checks.sh             # Execute all checks, output JSON
│   ├── severity-filter.sh        # Filter findings by severity
│   └── install-tools.sh          # Install missing tools
├── templates/
│   └── aidlc.yml.template        # Default .aidlc.yml config
└── tests/
    ├── test-detection.sh          # Detection engine tests
    ├── test-checks.sh             # Check runner tests
    ├── test-severity.sh           # Severity filter tests
    └── fixtures/
        ├── python-cdk/            # requirements.txt + cdk.json
        │   ├── requirements.txt
        │   ├── cdk.json
        │   └── app.py
        ├── typescript-next/       # package.json + tsconfig.json
        │   ├── package.json
        │   └── tsconfig.json
        └── go-terraform/          # go.mod + main.tf
            ├── go.mod
            └── main.tf
```

---

### Task 1: Initialize Repository and Plugin Manifest

**Files:**
- Create: `plugin.json`
- Create: `README.md`
- Create: `LICENSE`

- [ ] **Step 1: Create the GitHub repo**

```bash
mkdir -p ~/Fraser/Playground/aidlc-plugin && cd ~/Fraser/Playground/aidlc-plugin
git init
```

- [ ] **Step 2: Create plugin.json**

```json
{
  "name": "aidlc-plugin",
  "version": "0.1.0",
  "description": "AI Development Life Cycle — fully AI-driven dev workflow for Claude Code",
  "author": "Fraser27",
  "skills": [
    {
      "name": "aidlc-ship",
      "description": "Full lifecycle orchestrator: develop, check, review, fix, PR",
      "path": "skills/aidlc-ship.md"
    },
    {
      "name": "aidlc-review",
      "description": "Independent code review with no implementation context",
      "path": "skills/aidlc-review.md"
    },
    {
      "name": "aidlc-fix",
      "description": "Fix findings from AIDLC review",
      "path": "skills/aidlc-fix.md"
    },
    {
      "name": "aidlc-init",
      "description": "Detect project and scaffold .aidlc.yml config",
      "path": "skills/aidlc-init.md"
    },
    {
      "name": "aidlc-status",
      "description": "Show AIDLC cycle status and review history",
      "path": "skills/aidlc-status.md"
    }
  ],
  "hooks": {
    "pre-commit": "hooks/pre-commit.sh",
    "post-commit": "hooks/post-commit.sh"
  }
}
```

- [ ] **Step 3: Create LICENSE (MIT)**

```
MIT License

Copyright (c) 2026 Fraser27

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Create README.md**

```markdown
# AIDLC Plugin

AI Development Life Cycle plugin for Claude Code. Provides a fully AI-driven development workflow: develop, check, review, fix, and PR creation — all orchestrated by AI agents with human approval gates.

## Installation

\`\`\`bash
claude plugins add Fraser27/aidlc-plugin
\`\`\`

## Quick Start

Initialize AIDLC for your project:
\`\`\`
/aidlc-init
\`\`\`

Ship a feature (full lifecycle):
\`\`\`
/aidlc-ship "add retry logic to the query lambda"
\`\`\`

Review current branch independently:
\`\`\`
/aidlc-review
\`\`\`

## How It Works

1. **Develop** — Creates branch, implements change using TDD
2. **Self-Check** — Runs formatting, linting, type checks, tests, security, dep audit, IaC validation
3. **Review** — Spawns independent reviewer agent (no implementation context)
4. **Fix** — Addresses critical/high findings (max 3 cycles)
5. **Human Gate** — Presents summary, waits for approval
6. **PR Creation** — Creates PR with structured body

## Configuration

Create `.aidlc.yml` in your project root (or use `/aidlc-init`):

\`\`\`yaml
version: 1
tools:
  formatter: "ruff format"
  linter: "ruff check"
  test: "pytest --cov=. --cov-report=term-missing"
  security: "bandit -r ."
  type_check: "mypy ."
  iac_validate: "cdk synth --quiet"
  dep_audit: "pip-audit"
coverage:
  min: 80
  fail_on_drop: 5
review:
  threshold: "high"
  max_fix_cycles: 3
exclude:
  - "node_modules/"
  - ".venv/"
  - "cdk.out/"
branch_prefix: "aidlc"
\`\`\`

## Supported Languages

| Language | Formatter | Linter | Security | Types | Deps |
|----------|-----------|--------|----------|-------|------|
| Python | ruff format | ruff check | bandit | mypy | pip-audit |
| TypeScript/JS | prettier | eslint | semgrep | tsc | npm audit |
| Go | gofmt | golangci-lint | gosec | built-in | govulncheck |
| Rust | rustfmt | clippy | cargo-audit | built-in | cargo-audit |

## IaC Support

- AWS CDK (`cdk synth`)
- Terraform (`terraform validate`)
- SAM (`sam validate`)

## License

MIT
```

- [ ] **Step 5: Commit**

```bash
git add plugin.json README.md LICENSE
git commit -m "feat: initialize aidlc-plugin with manifest and docs"
```

---

### Task 2: Detection Engine Script

**Files:**
- Create: `scripts/detect-project.sh`

- [ ] **Step 1: Create test fixtures**

```bash
mkdir -p tests/fixtures/python-cdk tests/fixtures/typescript-next tests/fixtures/go-terraform
```

Create `tests/fixtures/python-cdk/requirements.txt`:
```
boto3==1.28.0
aws-cdk-lib==2.100.0
```

Create `tests/fixtures/python-cdk/cdk.json`:
```json
{"app": "python3 app.py"}
```

Create `tests/fixtures/python-cdk/app.py`:
```python
import aws_cdk as cdk
app = cdk.App()
```

Create `tests/fixtures/typescript-next/package.json`:
```json
{"name": "test-app", "dependencies": {"next": "14.0.0"}}
```

Create `tests/fixtures/typescript-next/tsconfig.json`:
```json
{"compilerOptions": {"strict": true}}
```

Create `tests/fixtures/go-terraform/go.mod`:
```
module example.com/infra
go 1.21
```

Create `tests/fixtures/go-terraform/main.tf`:
```hcl
resource "aws_instance" "example" {
  ami           = "ami-12345"
  instance_type = "t3.micro"
}
```

- [ ] **Step 2: Write detection test**

Create `tests/test-detection.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$SCRIPT_DIR/../scripts/detect-project.sh"
FIXTURES="$SCRIPT_DIR/fixtures"
PASS=0
FAIL=0

assert_contains() {
  local output="$1" expected="$2" context="$3"
  if echo "$output" | grep -q "$expected"; then
    ((PASS++))
  else
    echo "FAIL [$context]: expected '$expected' in output"
    echo "  Got: $output"
    ((FAIL++))
  fi
}

# Test Python CDK detection
echo "--- Testing Python CDK detection ---"
output=$("$DETECT" "$FIXTURES/python-cdk")
assert_contains "$output" '"language":"python"' "python-cdk language"
assert_contains "$output" '"formatter":"ruff format"' "python-cdk formatter"
assert_contains "$output" '"iac_validate":"cdk synth --quiet"' "python-cdk iac"
assert_contains "$output" '"security":"bandit"' "python-cdk security"

# Test TypeScript Next detection
echo "--- Testing TypeScript Next detection ---"
output=$("$DETECT" "$FIXTURES/typescript-next")
assert_contains "$output" '"language":"typescript"' "ts-next language"
assert_contains "$output" '"formatter":"prettier"' "ts-next formatter"
assert_contains "$output" '"linter":"eslint"' "ts-next linter"

# Test Go Terraform detection
echo "--- Testing Go Terraform detection ---"
output=$("$DETECT" "$FIXTURES/go-terraform")
assert_contains "$output" '"language":"go"' "go-tf language"
assert_contains "$output" '"formatter":"gofmt"' "go-tf formatter"
assert_contains "$output" '"iac_validate":"terraform validate"' "go-tf iac"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 3: Run test to verify it fails**

```bash
chmod +x tests/test-detection.sh
bash tests/test-detection.sh
```
Expected: FAIL (detect-project.sh doesn't exist yet)

- [ ] **Step 4: Write detect-project.sh**

Create `scripts/detect-project.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# detect-project.sh — Auto-detect project language, framework, and tools
# Usage: detect-project.sh [project_dir]
# Output: JSON tool profile to stdout

PROJECT_DIR="${1:-.}"

# Initialize detection results
LANGUAGE=""
FRAMEWORK=""
FORMATTER=""
LINTER=""
SECURITY=""
TYPE_CHECK=""
DEP_AUDIT=""
TEST_CMD=""
IAC_VALIDATE=""

# --- Language Detection ---

if [ -f "$PROJECT_DIR/requirements.txt" ] || [ -f "$PROJECT_DIR/pyproject.toml" ] || [ -f "$PROJECT_DIR/setup.py" ]; then
  LANGUAGE="python"
  FORMATTER="ruff format"
  LINTER="ruff check"
  SECURITY="bandit"
  TYPE_CHECK="mypy"
  DEP_AUDIT="pip-audit"
  TEST_CMD="pytest"
fi

if [ -f "$PROJECT_DIR/package.json" ]; then
  if [ -f "$PROJECT_DIR/tsconfig.json" ]; then
    LANGUAGE="typescript"
    TYPE_CHECK="tsc --noEmit"
  else
    LANGUAGE="javascript"
    TYPE_CHECK=""
  fi
  FORMATTER="prettier"
  LINTER="eslint"
  SECURITY="semgrep"
  DEP_AUDIT="npm audit"
  TEST_CMD="npm test"
fi

if [ -f "$PROJECT_DIR/go.mod" ]; then
  LANGUAGE="go"
  FORMATTER="gofmt"
  LINTER="golangci-lint run"
  SECURITY="gosec"
  TYPE_CHECK=""
  DEP_AUDIT="govulncheck"
  TEST_CMD="go test ./..."
fi

if [ -f "$PROJECT_DIR/Cargo.toml" ]; then
  LANGUAGE="rust"
  FORMATTER="rustfmt"
  LINTER="cargo clippy"
  SECURITY="cargo-audit"
  TYPE_CHECK=""
  DEP_AUDIT="cargo-audit"
  TEST_CMD="cargo test"
fi

# --- IaC Detection ---

if [ -f "$PROJECT_DIR/cdk.json" ]; then
  FRAMEWORK="cdk"
  IAC_VALIDATE="cdk synth --quiet"
fi

if compgen -G "$PROJECT_DIR/*.tf" > /dev/null 2>&1; then
  FRAMEWORK="terraform"
  IAC_VALIDATE="terraform validate"
fi

if [ -f "$PROJECT_DIR/template.yaml" ] || [ -f "$PROJECT_DIR/template.yml" ]; then
  if grep -q "AWS::Serverless" "$PROJECT_DIR/template.yaml" 2>/dev/null || grep -q "AWS::Serverless" "$PROJECT_DIR/template.yml" 2>/dev/null; then
    FRAMEWORK="sam"
    IAC_VALIDATE="sam validate"
  fi
fi

# --- Apply .aidlc.yml overrides if present ---

AIDLC_CONFIG="$PROJECT_DIR/.aidlc.yml"
if [ -f "$AIDLC_CONFIG" ]; then
  # Parse YAML overrides (simple key-value extraction)
  yaml_get() {
    grep "^  $1:" "$AIDLC_CONFIG" 2>/dev/null | sed 's/.*: *"\(.*\)"/\1/' | head -1
  }
  override=$(yaml_get "formatter") && [ -n "$override" ] && FORMATTER="$override"
  override=$(yaml_get "linter") && [ -n "$override" ] && LINTER="$override"
  override=$(yaml_get "security") && [ -n "$override" ] && SECURITY="$override"
  override=$(yaml_get "type_check") && [ -n "$override" ] && TYPE_CHECK="$override"
  override=$(yaml_get "dep_audit") && [ -n "$override" ] && DEP_AUDIT="$override"
  override=$(yaml_get "test") && [ -n "$override" ] && TEST_CMD="$override"
  override=$(yaml_get "iac_validate") && [ -n "$override" ] && IAC_VALIDATE="$override"
fi

# --- Output JSON ---

cat <<EOF
{"language":"${LANGUAGE}","framework":"${FRAMEWORK}","formatter":"${FORMATTER}","linter":"${LINTER}","security":"${SECURITY}","type_check":"${TYPE_CHECK}","dep_audit":"${DEP_AUDIT}","test":"${TEST_CMD}","iac_validate":"${IAC_VALIDATE}"}
EOF
```

- [ ] **Step 5: Run test to verify it passes**

```bash
chmod +x scripts/detect-project.sh
bash tests/test-detection.sh
```
Expected: All assertions pass

- [ ] **Step 6: Commit**

```bash
git add scripts/detect-project.sh tests/
git commit -m "feat: add detection engine with tests and fixtures"
```

---

### Task 3: Check Runner Script

**Files:**
- Create: `scripts/run-checks.sh`
- Create: `tests/test-checks.sh`

- [ ] **Step 1: Write check runner test**

Create `tests/test-checks.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_CHECKS="$SCRIPT_DIR/../scripts/run-checks.sh"
PASS=0
FAIL=0

assert_json_field() {
  local output="$1" field="$2" expected="$3" context="$4"
  local actual
  actual=$(echo "$output" | grep "\"check\":\"$field\"" || echo "")
  if [ -n "$actual" ]; then
    ((PASS++))
  else
    echo "FAIL [$context]: expected check '$field' in output"
    ((FAIL++))
  fi
}

# Test with a mock profile (dry-run mode)
echo "--- Testing check runner dry-run ---"
output=$("$RUN_CHECKS" --dry-run --profile '{"language":"python","formatter":"ruff format","linter":"ruff check","security":"bandit","type_check":"mypy","dep_audit":"pip-audit","test":"pytest","iac_validate":"cdk synth --quiet"}')
assert_json_field "$output" "format" "present" "format check listed"
assert_json_field "$output" "lint" "present" "lint check listed"
assert_json_field "$output" "security" "present" "security check listed"
assert_json_field "$output" "type_check" "present" "type check listed"
assert_json_field "$output" "test" "present" "test check listed"
assert_json_field "$output" "dep_audit" "present" "dep audit listed"
assert_json_field "$output" "iac_validate" "present" "iac check listed"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
chmod +x tests/test-checks.sh
bash tests/test-checks.sh
```
Expected: FAIL (run-checks.sh doesn't exist)

- [ ] **Step 3: Write run-checks.sh**

Create `scripts/run-checks.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# run-checks.sh — Execute all relevant checks based on project profile
# Usage: run-checks.sh [--dry-run] [--profile JSON] [--dir PROJECT_DIR]
# Output: One JSON object per line per check

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false
PROFILE=""
PROJECT_DIR="."

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY_RUN=true; shift ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --dir) PROJECT_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# If no profile provided, detect it
if [ -z "$PROFILE" ]; then
  PROFILE=$("$SCRIPT_DIR/detect-project.sh" "$PROJECT_DIR")
fi

# Extract fields from profile JSON (simple parsing)
json_get() {
  echo "$PROFILE" | sed 's/.*"'"$1"'":"\([^"]*\)".*/\1/'
}

FORMATTER=$(json_get "formatter")
LINTER=$(json_get "linter")
SECURITY=$(json_get "security")
TYPE_CHECK=$(json_get "type_check")
DEP_AUDIT=$(json_get "dep_audit")
TEST_CMD=$(json_get "test")
IAC_VALIDATE=$(json_get "iac_validate")

run_check() {
  local check_name="$1" tool="$2" command="$3" autofix="$4"

  if [ -z "$tool" ]; then
    return
  fi

  if [ "$DRY_RUN" = true ]; then
    echo "{\"check\":\"$check_name\",\"tool\":\"$tool\",\"command\":\"$command\",\"status\":\"dry-run\",\"findings\":[]}"
    return
  fi

  local output exit_code
  output=$(cd "$PROJECT_DIR" && eval "$command" 2>&1) && exit_code=0 || exit_code=$?

  if [ $exit_code -eq 0 ]; then
    echo "{\"check\":\"$check_name\",\"tool\":\"$tool\",\"status\":\"pass\",\"findings\":[]}"
  else
    echo "{\"check\":\"$check_name\",\"tool\":\"$tool\",\"status\":\"findings\",\"findings\":[{\"severity\":\"medium\",\"message\":$(echo "$output" | head -20 | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '\"check failed\"')}]}"
  fi
}

# Execute checks in order
run_check "format" "$FORMATTER" "$FORMATTER ." "true"
run_check "lint" "$LINTER" "$LINTER ." "true"
run_check "type_check" "$TYPE_CHECK" "$TYPE_CHECK ." "false"
run_check "test" "$TEST_CMD" "$TEST_CMD" "false"
run_check "security" "$SECURITY" "$SECURITY -r ." "false"
run_check "dep_audit" "$DEP_AUDIT" "$DEP_AUDIT" "false"
run_check "iac_validate" "$IAC_VALIDATE" "$IAC_VALIDATE" "false"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
chmod +x scripts/run-checks.sh
bash tests/test-checks.sh
```
Expected: All assertions pass

- [ ] **Step 5: Commit**

```bash
git add scripts/run-checks.sh tests/test-checks.sh
git commit -m "feat: add check runner with dry-run mode and tests"
```

---

### Task 4: Severity Filter Script

**Files:**
- Create: `scripts/severity-filter.sh`
- Create: `tests/test-severity.sh`

- [ ] **Step 1: Write severity filter test**

Create `tests/test-severity.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER="$SCRIPT_DIR/../scripts/severity-filter.sh"
PASS=0
FAIL=0

assert_eq() {
  local actual="$1" expected="$2" context="$3"
  if [ "$actual" = "$expected" ]; then
    ((PASS++))
  else
    echo "FAIL [$context]: expected '$expected', got '$actual'"
    ((FAIL++))
  fi
}

# Test filtering high findings
echo "--- Testing severity filter ---"
INPUT='{"check":"security","tool":"bandit","status":"findings","findings":[{"severity":"high","message":"eval detected"},{"severity":"low","message":"naming"}]}'

high_count=$(echo "$INPUT" | "$FILTER" --level high | grep -c '"severity":"high"' || echo "0")
assert_eq "$high_count" "1" "high filter count"

all_count=$(echo "$INPUT" | "$FILTER" --level all | grep -c '"severity"' || echo "0")
assert_eq "$all_count" "2" "all filter count"

# Test exit code (should be non-zero if blocking findings exist)
echo "$INPUT" | "$FILTER" --level high --exit-code && ec=$? || ec=$?
assert_eq "$ec" "1" "exit code on high findings"

CLEAN='{"check":"lint","tool":"ruff","status":"pass","findings":[]}'
echo "$CLEAN" | "$FILTER" --level high --exit-code && ec=$? || ec=$?
assert_eq "$ec" "0" "exit code on clean"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
chmod +x tests/test-severity.sh
bash tests/test-severity.sh
```
Expected: FAIL

- [ ] **Step 3: Write severity-filter.sh**

Create `scripts/severity-filter.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# severity-filter.sh — Filter check findings by severity level
# Usage: echo '<check_output>' | severity-filter.sh --level high [--exit-code]
# Levels: high (high+critical), medium (medium+high+critical), all
# --exit-code: exit non-zero if blocking findings exist at the specified level

LEVEL="high"
EXIT_CODE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --level) LEVEL="$2"; shift 2 ;;
    --exit-code) EXIT_CODE=true; shift ;;
    *) shift ;;
  esac
done

# Read all input
INPUT=$(cat)

# Define severity patterns based on level
case "$LEVEL" in
  high)    PATTERN='"severity":"(high|critical)"' ;;
  medium)  PATTERN='"severity":"(high|critical|medium)"' ;;
  all)     PATTERN='"severity":"(high|critical|medium|low)"' ;;
  *)       echo "Unknown level: $LEVEL" >&2; exit 2 ;;
esac

# Filter and output matching findings
FILTERED=$(echo "$INPUT" | grep -oE '\{"severity":"[^"]+","[^}]+\}' | grep -E "$PATTERN" || true)

if [ -n "$FILTERED" ]; then
  echo "$FILTERED"
  if [ "$EXIT_CODE" = true ]; then
    exit 1
  fi
else
  if [ "$EXIT_CODE" = true ]; then
    exit 0
  fi
fi
```

- [ ] **Step 4: Run test to verify it passes**

```bash
chmod +x scripts/severity-filter.sh
bash tests/test-severity.sh
```
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add scripts/severity-filter.sh tests/test-severity.sh
git commit -m "feat: add severity filter with level-based blocking"
```

---

### Task 5: Install Tools Script

**Files:**
- Create: `scripts/install-tools.sh`

- [ ] **Step 1: Write install-tools.sh**

Create `scripts/install-tools.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# install-tools.sh — Check for and install missing tools
# Usage: install-tools.sh [--profile JSON] [--auto]
# --auto: install without prompting (for CI)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE=""
AUTO=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --auto) AUTO=true; shift ;;
    *) shift ;;
  esac
done

if [ -z "$PROFILE" ]; then
  PROFILE=$("$SCRIPT_DIR/detect-project.sh" ".")
fi

json_get() {
  echo "$PROFILE" | sed 's/.*"'"$1"'":"\([^"]*\)".*/\1/'
}

LANGUAGE=$(json_get "language")
MISSING=()

check_tool() {
  local tool_name="$1" binary="$2"
  if [ -z "$binary" ]; then return; fi
  # Extract first word as the binary name
  local cmd
  cmd=$(echo "$binary" | awk '{print $1}')
  if ! command -v "$cmd" &>/dev/null; then
    MISSING+=("$tool_name:$binary")
    echo "MISSING: $cmd (needed for $tool_name)"
  else
    echo "OK: $cmd"
  fi
}

echo "=== Checking tools for $LANGUAGE project ==="
check_tool "formatter" "$(json_get 'formatter')"
check_tool "linter" "$(json_get 'linter')"
check_tool "security" "$(json_get 'security')"
check_tool "type_check" "$(json_get 'type_check')"
check_tool "dep_audit" "$(json_get 'dep_audit')"
check_tool "test" "$(json_get 'test')"
check_tool "iac_validate" "$(json_get 'iac_validate')"

if [ ${#MISSING[@]} -eq 0 ]; then
  echo ""
  echo "All tools installed."
  exit 0
fi

echo ""
echo "=== Missing tools ==="
for item in "${MISSING[@]}"; do
  echo "  - ${item%%:*}: ${item##*:}"
done

# Suggest install commands
echo ""
echo "=== Suggested install commands ==="
case "$LANGUAGE" in
  python)
    echo "pip install ruff bandit mypy pip-audit pytest pytest-cov"
    if [ "$AUTO" = true ]; then
      pip install ruff bandit mypy pip-audit pytest pytest-cov
    fi
    ;;
  typescript|javascript)
    echo "npm install -D prettier eslint typescript @semgrep/cli"
    if [ "$AUTO" = true ]; then
      npm install -D prettier eslint typescript
    fi
    ;;
  go)
    echo "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"
    echo "go install github.com/securego/gosec/v2/cmd/gosec@latest"
    echo "go install golang.org/x/vuln/cmd/govulncheck@latest"
    if [ "$AUTO" = true ]; then
      go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
      go install github.com/securego/gosec/v2/cmd/gosec@latest
      go install golang.org/x/vuln/cmd/govulncheck@latest
    fi
    ;;
  rust)
    echo "rustup component add rustfmt clippy"
    echo "cargo install cargo-audit"
    if [ "$AUTO" = true ]; then
      rustup component add rustfmt clippy
      cargo install cargo-audit
    fi
    ;;
esac
```

- [ ] **Step 2: Commit**

```bash
chmod +x scripts/install-tools.sh
git add scripts/install-tools.sh
git commit -m "feat: add install-tools script with auto-detection"
```

---

### Task 6: Config Template

**Files:**
- Create: `templates/aidlc.yml.template`

- [ ] **Step 1: Write template**

Create `templates/aidlc.yml.template`:
```yaml
# .aidlc.yml — AIDLC Plugin Configuration
# Generated by /aidlc-init
version: 1

# Override auto-detected tools (uncomment to customize)
# tools:
#   formatter: "ruff format"
#   linter: "ruff check"
#   test: "pytest --cov=. --cov-report=term-missing"
#   security: "bandit -r ."
#   type_check: "mypy ."
#   iac_validate: "cdk synth --quiet"
#   dep_audit: "pip-audit"

# Coverage thresholds
coverage:
  min: 80
  fail_on_drop: 5

# Review settings
review:
  threshold: "high"    # block on: high, medium, or all
  max_fix_cycles: 3

# Excluded paths (not scanned)
exclude:
  - "node_modules/"
  - ".venv/"
  - "cdk.out/"
  - "__pycache__/"
  - ".git/"

# Custom checks (run during check phase)
# custom_checks:
#   - name: "cdk diff"
#     command: "cdk diff 2>&1"
#     severity: "medium"

# Branch naming prefix
branch_prefix: "aidlc"
```

- [ ] **Step 2: Commit**

```bash
git add templates/aidlc.yml.template
git commit -m "feat: add .aidlc.yml config template"
```

---

### Task 7: Pre-commit Hook

**Files:**
- Create: `hooks/pre-commit.sh`

- [ ] **Step 1: Write pre-commit.sh**

Create `hooks/pre-commit.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# AIDLC pre-commit hook — format and lint staged files
# Blocks commit if unfixable lint errors remain

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$SCRIPT_DIR/../scripts/detect-project.sh"
PROJECT_DIR="$(git rev-parse --show-toplevel)"

# Detect project tools
PROFILE=$("$DETECT" "$PROJECT_DIR")

json_get() {
  echo "$PROFILE" | sed 's/.*"'"$1"'":"\([^"]*\)".*/\1/'
}

FORMATTER=$(json_get "formatter")
LINTER=$(json_get "linter")

echo "[AIDLC] Running pre-commit checks..."

# Get staged files
STAGED=$(git diff --cached --name-only --diff-filter=ACMR)
if [ -z "$STAGED" ]; then
  exit 0
fi

# --- Format ---
if [ -n "$FORMATTER" ] && command -v "$(echo "$FORMATTER" | awk '{print $1}')" &>/dev/null; then
  echo "[AIDLC] Formatting..."
  (cd "$PROJECT_DIR" && eval "$FORMATTER .") 2>/dev/null || true
  # Re-stage formatted files
  echo "$STAGED" | while read -r file; do
    [ -f "$PROJECT_DIR/$file" ] && git add "$PROJECT_DIR/$file"
  done
fi

# --- Lint ---
if [ -n "$LINTER" ] && command -v "$(echo "$LINTER" | awk '{print $1}')" &>/dev/null; then
  echo "[AIDLC] Linting..."
  # Try auto-fix first
  (cd "$PROJECT_DIR" && eval "$LINTER --fix ." 2>/dev/null) || true
  # Re-stage fixed files
  echo "$STAGED" | while read -r file; do
    [ -f "$PROJECT_DIR/$file" ] && git add "$PROJECT_DIR/$file"
  done
  # Check for remaining errors
  if ! (cd "$PROJECT_DIR" && eval "$LINTER ." >/dev/null 2>&1); then
    echo "[AIDLC] Lint errors remain after auto-fix. Blocking commit."
    (cd "$PROJECT_DIR" && eval "$LINTER .") || true
    exit 1
  fi
fi

echo "[AIDLC] Pre-commit checks passed."
```

- [ ] **Step 2: Commit**

```bash
chmod +x hooks/pre-commit.sh
git add hooks/pre-commit.sh
git commit -m "feat: add pre-commit hook for format and lint"
```

---

### Task 8: Post-commit Hook

**Files:**
- Create: `hooks/post-commit.sh`

- [ ] **Step 1: Write post-commit.sh**

Create `hooks/post-commit.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# AIDLC post-commit hook — run security scan on changed files (warn only)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$SCRIPT_DIR/../scripts/detect-project.sh"
PROJECT_DIR="$(git rev-parse --show-toplevel)"

# Detect project tools
PROFILE=$("$DETECT" "$PROJECT_DIR")

json_get() {
  echo "$PROFILE" | sed 's/.*"'"$1"'":"\([^"]*\)".*/\1/'
}

SECURITY=$(json_get "security")

if [ -z "$SECURITY" ]; then
  exit 0
fi

SECURITY_CMD=$(echo "$SECURITY" | awk '{print $1}')
if ! command -v "$SECURITY_CMD" &>/dev/null; then
  exit 0
fi

# Get files changed in last commit
CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)
if [ -z "$CHANGED" ]; then
  exit 0
fi

echo "[AIDLC] Running security scan on committed files..."

# Run security scan (non-blocking, just warn)
OUTPUT=$(cd "$PROJECT_DIR" && eval "$SECURITY -r ." 2>&1) || true

if echo "$OUTPUT" | grep -qiE "(high|critical|severe)"; then
  echo "[AIDLC] WARNING: Security findings detected in committed code."
  echo "$OUTPUT" | head -20
  echo "[AIDLC] Run '/aidlc-review' for full analysis."
fi
```

- [ ] **Step 2: Commit**

```bash
chmod +x hooks/post-commit.sh
git add hooks/post-commit.sh
git commit -m "feat: add post-commit hook for security scan warnings"
```

---

### Task 9: `/aidlc-init` Skill

**Files:**
- Create: `skills/aidlc-init.md`

- [ ] **Step 1: Write aidlc-init.md**

Create `skills/aidlc-init.md`:
```markdown
---
name: aidlc-init
description: Detect project and scaffold .aidlc.yml config
---

# AIDLC Init

Initialize AIDLC for the current project. Detects language, framework, and tools, then generates a `.aidlc.yml` configuration file.

## Steps

1. **Detect project type**

Run the detection script:
\`\`\`bash
PLUGIN_DIR="$(dirname "$(dirname "${BASH_SOURCE[0]}")")"
$PLUGIN_DIR/scripts/detect-project.sh .
\`\`\`

Present the detected profile to the user:
- Language: {detected language}
- Framework: {detected framework}
- Tools: formatter, linter, security, type_check, dep_audit, test, iac_validate

2. **Check for missing tools**

Run:
\`\`\`bash
$PLUGIN_DIR/scripts/install-tools.sh --profile "$PROFILE"
\`\`\`

If tools are missing, ask the user if they want to install them. If yes, run:
\`\`\`bash
$PLUGIN_DIR/scripts/install-tools.sh --profile "$PROFILE" --auto
\`\`\`

3. **Generate .aidlc.yml**

Read the template from `$PLUGIN_DIR/templates/aidlc.yml.template`.

Customize it based on detected profile:
- Uncomment the tools section and fill in detected values
- Set exclude paths appropriate to the detected language/framework
- If CDK project, add `cdk.out/` to excludes
- If Node project, add `node_modules/` and `dist/` to excludes

Present the generated config to the user for approval before writing.

4. **Write config**

After user approves, write `.aidlc.yml` to the project root.

5. **Create .aidlc/ directory**

\`\`\`bash
mkdir -p .aidlc/reviews
echo "reviews/" > .aidlc/.gitignore
\`\`\`

6. **Summary**

Tell the user:
- AIDLC initialized for {language} {framework} project
- Config written to `.aidlc.yml`
- Use `/aidlc-ship "description"` to start the full lifecycle
- Use `/aidlc-review` for standalone code review
```

- [ ] **Step 2: Commit**

```bash
git add skills/aidlc-init.md
git commit -m "feat: add /aidlc-init skill for project scaffolding"
```

---

### Task 10: `/aidlc-review` Skill

**Files:**
- Create: `skills/aidlc-review.md`

- [ ] **Step 1: Write aidlc-review.md**

Create `skills/aidlc-review.md`:
```markdown
---
name: aidlc-review
description: Independent code review with no implementation context
---

# AIDLC Review

You are an independent code reviewer. You have NO context about WHY these changes were made or what shortcuts were considered. Review purely based on what you see in the diff.

## CRITICAL: Separation Principle

You must NOT ask about or consider:
- The original implementation prompt
- Why the developer chose this approach
- Trade-offs that were discussed

You review ONLY what is in the code. This prevents author bias.

## Steps

1. **Get the diff**

Determine what to review:
- If on a feature branch: `git diff main...HEAD`
- If specific files mentioned: review those files
- If PR number given: `gh pr diff <number>`

```bash
DIFF=$(git diff main...HEAD)
BRANCH=$(git branch --show-current)
```

2. **Read full file context**

For each file in the diff, read the complete file (not just the diff) to understand surrounding context.

3. **Review against checklist**

Evaluate the changes against each criterion:

### Correctness
- Does the code do what it claims?
- Edge cases handled? Off-by-one errors?
- Null/undefined/empty states considered?

### Security
- Injection risks (SQL, command, XSS)?
- Authentication/authorization gaps?
- Secrets or credentials exposed?
- OWASP top 10 violations?

### Performance
- N+1 query patterns?
- Unnecessary loops or allocations?
- Missing caching opportunities?
- Unbounded operations?

### Error Handling
- Unhappy paths covered?
- Graceful degradation?
- Error messages helpful for debugging?

### Readability
- Could another dev understand this in 6 months?
- Names communicate intent?
- Complex logic has comments?

### Testing
- Tests cover the change?
- Tests are meaningful (not just asserting true)?
- Edge cases tested?

### IaC Concerns (if applicable)
- Overly permissive IAM policies?
- Resources publicly accessible that shouldn't be?
- Missing encryption at rest/in transit?
- No resource limits/quotas?

4. **Classify findings by severity**

- **HIGH/CRITICAL**: Security vulnerabilities, data loss risks, broken functionality, hardcoded secrets
- **MEDIUM**: Performance issues, missing error handling, incomplete edge cases, weak typing
- **LOW**: Style issues formatter missed, minor naming improvements, documentation gaps

5. **Write review output**

Write to `.aidlc/reviews/{branch}-{timestamp}.md`:

```markdown
# AIDLC Review — {branch}
**Date:** {timestamp}
**Files reviewed:** {count}
**Reviewer:** AIDLC Independent Agent

## Critical/High (must fix)
- [HIGH] {file}:{line} — {description}

## Medium (consider)
- [MED] {file}:{line} — {description}

## Low (noted)
- [LOW] {file}:{line} — {description}

## Summary
{high_count} high, {med_count} medium, {low_count} low findings.
{blocking_statement}
```

6. **Present to user**

Display the review summary. If there are high/critical findings, clearly state:
"Blocking on {n} high-severity issue(s). These must be fixed before merging."

If only medium/low: "No blocking issues. {n} suggestions for consideration."
```

- [ ] **Step 2: Commit**

```bash
git add skills/aidlc-review.md
git commit -m "feat: add /aidlc-review skill for independent code review"
```

---

### Task 11: `/aidlc-fix` Skill

**Files:**
- Create: `skills/aidlc-fix.md`

- [ ] **Step 1: Write aidlc-fix.md**

Create `skills/aidlc-fix.md`:
```markdown
---
name: aidlc-fix
description: Fix findings from AIDLC review
---

# AIDLC Fix

Address findings from an AIDLC review. Focus on high/critical findings first, then medium if time permits.

## Steps

1. **Load review findings**

Read the latest review file:
```bash
LATEST_REVIEW=$(ls -t .aidlc/reviews/*.md 2>/dev/null | head -1)
```

If no review exists, tell the user to run `/aidlc-review` first.

2. **Parse findings by severity**

Extract all HIGH/CRITICAL findings — these MUST be fixed.
Extract MEDIUM findings — these SHOULD be fixed if straightforward.
Ignore LOW findings.

3. **Fix high/critical findings**

For each high/critical finding:
- Read the referenced file and line
- Understand the issue
- Implement the fix
- Ensure the fix doesn't introduce new issues

4. **Fix medium findings (if straightforward)**

For each medium finding:
- If the fix is < 5 lines and clearly correct, fix it
- If the fix requires design decisions, skip and note it

5. **Run checks after fixing**

```bash
$PLUGIN_DIR/scripts/run-checks.sh --dir .
```

Verify no new high/critical findings were introduced by the fixes.

6. **Commit fixes**

```bash
git add -A
git commit -m "fix: address AIDLC review findings

Fixed:
- {list of HIGH findings fixed}

Acknowledged (medium):
- {list of MEDIUM findings noted but not fixed, with reasoning}
"
```

7. **Report**

Tell the user what was fixed, what was acknowledged, and whether re-review is needed.
```

- [ ] **Step 2: Commit**

```bash
git add skills/aidlc-fix.md
git commit -m "feat: add /aidlc-fix skill for addressing review findings"
```

---

### Task 12: `/aidlc-ship` Orchestrator Skill

**Files:**
- Create: `skills/aidlc-ship.md`

- [ ] **Step 1: Write aidlc-ship.md**

Create `skills/aidlc-ship.md`:
```markdown
---
name: aidlc-ship
description: Full lifecycle orchestrator - develop, check, review, fix, PR
---

# AIDLC Ship

Full AI Development Life Cycle orchestrator. Takes a feature description and handles the entire workflow: branch creation, implementation, checks, independent review, fixing, and PR creation.

## Usage

```
/aidlc-ship "description of what to implement"
```

## Prerequisites

- Project must have `.aidlc.yml` (run `/aidlc-init` first if not present)
- Must be on a clean working tree (no uncommitted changes)

## Orchestration Flow

### Phase 1: SETUP

```bash
# Verify clean state
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: Working tree is dirty. Commit or stash changes first."
  exit 1
fi

# Determine base branch
BASE_BRANCH=$(git branch --show-current)

# Read config
AIDLC_CONFIG=".aidlc.yml"
BRANCH_PREFIX="aidlc"
if [ -f "$AIDLC_CONFIG" ]; then
  PREFIX=$(grep "branch_prefix:" "$AIDLC_CONFIG" | awk '{print $2}' | tr -d '"')
  [ -n "$PREFIX" ] && BRANCH_PREFIX="$PREFIX"
fi

# Create feature branch
SLUG=$(echo "{description}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | cut -c1-40)
BRANCH="${BRANCH_PREFIX}/${SLUG}"
git checkout -b "$BRANCH"
```

### Phase 2: DEVELOP

Implement the requested change:

1. Understand the request from the user's description
2. Read relevant existing code to understand the codebase
3. If tests exist in the project, use TDD:
   - Write failing test first
   - Implement minimal code to pass
   - Refactor if needed
4. If no test infrastructure exists, implement directly
5. Run format and lint (auto-fix):
   ```bash
   $PLUGIN_DIR/scripts/run-checks.sh --dir . --profile "$PROFILE"
   ```
6. Commit working code:
   ```bash
   git add -A
   git commit -m "feat: {description}"
   ```

### Phase 3: SELF-CHECK

Run the full check suite:

```bash
RESULTS=$($PLUGIN_DIR/scripts/run-checks.sh --dir .)
HIGH_FINDINGS=$(echo "$RESULTS" | $PLUGIN_DIR/scripts/severity-filter.sh --level high)
```

- If HIGH findings exist → go to Phase 4 (FIX) targeting these findings
- If only MEDIUM/LOW → proceed to Phase 4 (REVIEW)

### Phase 4: REVIEW

Spawn an independent reviewer subagent:

**CRITICAL:** The reviewer subagent must:
- Receive ONLY the git diff (`git diff $BASE_BRANCH...HEAD`)
- Have NO access to this orchestration prompt or the original feature request
- Use the `/aidlc-review` skill

Use the Agent tool with subagent_type to spawn the reviewer:
```
Invoke Agent tool:
  prompt: "Run /aidlc-review on the current branch. Review the diff against main. Write findings to .aidlc/reviews/"
  subagent_type: "Explore"
```

After the reviewer completes, read the review file from `.aidlc/reviews/`.

### Phase 5: FIX (if needed)

Read the review findings. If HIGH/CRITICAL findings exist:

1. Fix each high/critical finding
2. Re-run checks
3. Commit fixes
4. **Cycle counter:** Track fix iterations

```
FIX_CYCLE=1
MAX_CYCLES=3  # from .aidlc.yml review.max_fix_cycles
```

If after fixing, re-review still finds HIGH issues:
- Increment FIX_CYCLE
- If FIX_CYCLE > MAX_CYCLES: **ESCALATE TO HUMAN**
  - Present all remaining findings
  - Ask for guidance
  - Do NOT continue automatically

If all HIGH findings resolved → proceed to Phase 6.

### Phase 6: HUMAN GATE

**STOP HERE. Present to the user:**

```markdown
## AIDLC Ship Summary — {branch}

### Changes Made
- {summary of implementation}

### Check Results
- Format: PASS
- Lint: PASS
- Types: PASS
- Tests: PASS (coverage: X%)
- Security: {PASS or N warnings}
- Deps: PASS
- IaC: PASS

### Review Findings
- High/Critical: 0 (all resolved)
- Medium: {count} (noted below)
  - {list of medium findings}
- Low: {count}

### Ready to create PR?
Approve to create PR, or provide feedback for changes.
```

**Wait for user response.** Do NOT proceed without explicit approval.

### Phase 7: PR CREATION

After user approves:

```bash
git push -u origin "$BRANCH"

gh pr create --title "{short description}" --body "$(cat <<'EOF'
## Summary
{1-3 bullet points of what was implemented}

## AIDLC Check Results
- Format: PASS
- Lint: PASS
- Types: PASS
- Tests: PASS (coverage: X%)
- Security: PASS
- Deps: PASS
- IaC: PASS

## Review Notes
{medium findings listed as "known considerations"}

## Test Plan
- {how to verify this works}

---
Shipped with [AIDLC](https://github.com/Fraser27/aidlc-plugin)
EOF
)"
```

Present the PR URL to the user.

## Error Handling

- If implementation fails: present the error, ask user for guidance
- If checks can't run (missing tools): offer to install via `install-tools.sh`
- If review subagent fails: fall back to self-review (note this to user)
- If PR creation fails: show the error, suggest manual steps
```

- [ ] **Step 2: Commit**

```bash
git add skills/aidlc-ship.md
git commit -m "feat: add /aidlc-ship orchestrator skill"
```

---

### Task 13: `/aidlc-status` Skill

**Files:**
- Create: `skills/aidlc-status.md`

- [ ] **Step 1: Write aidlc-status.md**

Create `skills/aidlc-status.md`:
```markdown
---
name: aidlc-status
description: Show AIDLC cycle status and review history
---

# AIDLC Status

Show the current state of AIDLC in this project.

## Steps

1. **Check initialization**

```bash
if [ ! -f ".aidlc.yml" ]; then
  echo "AIDLC not initialized. Run /aidlc-init first."
  exit 0
fi
```

2. **Show project profile**

Run detection and display:
```bash
$PLUGIN_DIR/scripts/detect-project.sh .
```

3. **Show current branch status**

```bash
BRANCH=$(git branch --show-current)
echo "Current branch: $BRANCH"
```

If on an aidlc/* branch, show:
- Commits since branching from main
- Whether checks have been run
- Whether review exists

4. **Show review history**

```bash
ls -lt .aidlc/reviews/*.md 2>/dev/null | head -5
```

For each recent review, show:
- Date
- Branch
- Finding counts (high/med/low)

5. **Show tool status**

Run install-tools.sh in check-only mode and report which tools are available vs missing.

6. **Present summary**

Format as:
```markdown
## AIDLC Status

**Project:** {language} / {framework}
**Config:** .aidlc.yml (present)
**Branch:** {current branch}
**Tools:** {n}/{total} installed

### Recent Reviews
| Date | Branch | High | Med | Low |
|------|--------|------|-----|-----|
| ... | ... | ... | ... | ... |

### Suggested Actions
- {contextual suggestions based on state}
```
```

- [ ] **Step 2: Commit**

```bash
git add skills/aidlc-status.md
git commit -m "feat: add /aidlc-status skill for cycle visibility"
```

---

### Task 14: Push to GitHub

**Files:** None (repo management)

- [ ] **Step 1: Create GitHub repo**

```bash
gh repo create Fraser27/aidlc-plugin --public --description "AI Development Life Cycle plugin for Claude Code" --source . --push
```

- [ ] **Step 2: Verify repo is live**

```bash
gh repo view Fraser27/aidlc-plugin
```

---

### Task 15: Test with serverless-rag-demo

**Files:**
- Create: `/Users/fraseque/Fraser/Playground/serverless-rag-demo/.aidlc.yml`

- [ ] **Step 1: Install the plugin**

```bash
claude plugins add Fraser27/aidlc-plugin
```

- [ ] **Step 2: Run /aidlc-init in the serverless-rag-demo project**

```bash
cd /Users/fraseque/Fraser/Playground/serverless-rag-demo
# Then in Claude Code: /aidlc-init
```

- [ ] **Step 3: Verify detection**

Expected detection for serverless-rag-demo:
- Language: python
- Framework: cdk
- Formatter: ruff format
- Linter: ruff check
- Security: bandit
- Type check: mypy
- Tests: pytest
- IaC: cdk synth --quiet

- [ ] **Step 4: Run /aidlc-ship with a small change**

```
/aidlc-ship "add type hints to app.py"
```

Verify the full cycle executes: branch → implement → check → review → fix → human gate → PR.

---

## Execution Notes

- Tasks 1-13 all happen in `~/Fraser/Playground/aidlc-plugin/`
- Task 14 pushes to GitHub
- Task 15 tests the plugin against the real project
- Each task is independent except Task 14 depends on 1-13, and Task 15 depends on 14
