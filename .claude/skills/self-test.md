---
name: self-test
description: Run tests, generate new test cases, validate changes, and produce coverage reports. Identifies regressions and categorizes failures.
user_invocable: true
---

# Self-Test — Testing & Validation

Run the full test suite, generate missing tests, validate recent changes, and produce actionable reports.

## When to Use

- After `self-implement` makes code changes
- To check for regressions
- To generate tests for untested code
- As the validation phase of the self-loop

## Test Execution

### Phase 1: Run Existing Tests

```bash
# Python tests
cd /path/to/project
python -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/test_results.txt

# If no tests/ directory, try:
python -m pytest app/ -v --tb=short 2>&1 | tee /tmp/test_results.txt

# Frontend tests (if applicable)
cd frontend && npm test -- --watchAll=false 2>&1 | tee /tmp/frontend_test_results.txt
```

### Phase 2: Linting & Type Checking

```bash
# Python linting
python -m flake8 app/ --max-line-length=120 --ignore=E501,W503 2>&1 | tee /tmp/lint_results.txt

# Python type checking
python -m mypy app/ --ignore-missing-imports 2>&1 | tee /tmp/mypy_results.txt

# Frontend linting
cd frontend && npx eslint src/ --ext .ts,.tsx 2>&1 | tee /tmp/frontend_lint_results.txt
```

### Phase 3: Coverage Analysis

```bash
# Python coverage
python -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=json:/tmp/coverage.json 2>&1 | tee /tmp/coverage_results.txt

# Parse uncovered lines for critical files
python3 -c "
import json
cov = json.load(open('/tmp/coverage.json'))
for f, data in cov.get('files', {}).items():
    missing = data.get('missing_lines', [])
    total = data.get('summary', {}).get('num_statements', 0)
    if total > 0 and len(missing) > 0:
        pct = (total - len(missing)) / total * 100
        if pct < 80:
            print(f'LOW COVERAGE ({pct:.0f}%): {f} — missing lines: {missing[:10]}')
"
```

### Phase 4: API Validation

```bash
# Check if server starts without errors
timeout 10 python -c "from app.main import app; print('App loads OK')" 2>&1

# Validate all routes are registered
python3 -c "
from app.main import app
for route in app.routes:
    if hasattr(route, 'methods'):
        print(f'{route.methods} {route.path}')
"
```

## Test Generation

For files with low coverage, generate tests:

### Strategy

1. **Read the source file** completely
2. **Identify testable units:**
   - Pure functions (input → output)
   - Service methods (with DB/network mocking)
   - API endpoints (via test client)
3. **For each unit, generate:**
   - Happy path test
   - Error/edge case tests
   - Boundary condition tests
4. **Follow existing test patterns** in the project

### Test Generation Template

For API endpoints:
```python
"""Tests for {endpoint} endpoint."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class Test{EndpointName}:
    """Tests for {method} {path}."""

    def test_success(self):
        """Valid request returns expected response."""
        response = client.{method}("{path}", json={valid_payload})
        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data

    def test_missing_required_field(self):
        """Missing field returns 422."""
        response = client.{method}("{path}", json={invalid_payload})
        assert response.status_code == 422

    def test_not_found(self):
        """Non-existent resource returns 404."""
        response = client.{method}("{path}/99999")
        assert response.status_code == 404

    def test_invalid_input(self):
        """Invalid input returns 400."""
        response = client.{method}("{path}", json={bad_payload})
        assert response.status_code in (400, 422)
```

For service functions:
```python
"""Tests for {service_name}."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.{module} import {function}


class Test{FunctionName}:
    """Tests for {function_name}."""

    @patch("app.services.{module}.dependency")
    def test_success(self, mock_dep):
        """Normal operation returns expected result."""
        mock_dep.return_value = {mock_value}
        result = {function}({input})
        assert result == {expected}

    @patch("app.services.{module}.dependency")
    def test_dependency_failure(self, mock_dep):
        """Dependency failure handled gracefully."""
        mock_dep.side_effect = Exception("DB error")
        with pytest.raises(Exception):
            {function}({input})
```

## Failure Categorization

Parse test output and categorize failures:

| Category | Pattern | Action |
|----------|---------|--------|
| **Regression** | Test was passing, now fails | High priority fix |
| **New Bug** | New test fails on new code | Fix in self-fix |
| **Environment** | Import error, missing dep | Install/configure |
| **Flaky** | Intermittent failure | Retry, then investigate |
| **Expected** | Test needs updating | Update test assertion |

## Output Format

Write results to `memory/test-report.md`:

```markdown
# Test Report — YYYY-MM-DD HH:MM

## Summary
- **Passed:** N
- **Failed:** N
- **Errors:** N
- **Skipped:** N
- **Coverage:** XX%

## Failures

### [REGRESSION] test_employee_update
- **File:** tests/test_employee.py:45
- **Error:** AssertionError: expected 200, got 500
- **Category:** regression
- **Likely cause:** Missing null check in update_employee

### [NEW] test_batch_parse_empty
- **File:** tests/test_batch_parser.py:12
- **Error:** ValueError not raised
- **Category:** new-bug
- **Likely cause:** Missing validation in extract_profiles_from_text

## Coverage Gaps (files < 80%)
- app/services/batch_parser.py (45%)
- app/services/llm_extractor.py (60%)

## Recommendations
1. Fix regression in test_employee_update (high priority)
2. Add tests for batch_parser.py (medium priority)
3. Update flaky test test_metrics_weekly (low priority)
```

## Integration

- `self-implement` triggers this after code changes
- `self-fix` reads failures from the test report
- `self-loop` uses this to validate each iteration
