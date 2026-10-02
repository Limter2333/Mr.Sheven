#!/usr/bin/env bash
# scan_codebase.sh — Scan project for TODOs, missing tests, code smells
# Usage: bash .claude/skills/scripts/scan_codebase.sh [--all|--todo|--tests|--smells|--coverage]
set -euo pipefail

PROJECT_ROOT="${1:-.}"
MODE="${2:---all}"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

separator() { echo -e "${CYAN}────────────────────────────────────────${NC}"; }

# ── TODO/FIXME/HACK Scan ──
scan_todos() {
    separator
    echo -e "${CYAN}[TODO/FIXME/HACK SCAN]${NC}"
    separator

    local count=0
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            echo -e "${YELLOW}$line${NC}"
            ((count++))
        fi
    done < <(grep -rn "TODO\|FIXME\|HACK\|XXX\|TEMP\|WORKAROUND" \
        --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
        "$PROJECT_ROOT/app" "$PROJECT_ROOT/src" "$PROJECT_ROOT/frontend/src" \
        --color=never 2>/dev/null || true)

    echo -e "\n${GREEN}Found $count TODO/FIXME items${NC}"
}

# ── Missing Tests Scan ──
scan_missing_tests() {
    separator
    echo -e "${CYAN}[MISSING TEST COVERAGE]${NC}"
    separator

    local count=0

    # Python files without tests
    if [ -d "$PROJECT_ROOT/app" ]; then
        while IFS= read -r f; do
            base=$(basename "$f" .py)
            test_file="$PROJECT_ROOT/tests/test_${base}.py"
            if [ ! -f "$test_file" ]; then
                echo -e "${RED}NO TEST:${NC} $f"
                ((count++))
            fi
        done < <(find "$PROJECT_ROOT/app" -name "*.py" ! -name "__init__.py" 2>/dev/null)
    fi

    # Frontend files without tests
    if [ -d "$PROJECT_ROOT/frontend/src" ]; then
        while IFS= read -r f; do
            base=$(basename "$f" | sed 's/\.\(tsx\|ts\|jsx\|js\)$//')
            dir=$(dirname "$f")
            if [ ! -f "${dir}/${base}.test.tsx" ] && [ ! -f "${dir}/${base}.test.ts" ] && \
               [ ! -f "${dir}/${base}.test.jsx" ] && [ ! -f "${dir}/${base}.test.js" ] && \
               [ ! -f "${dir}/__tests__/${base}.test.tsx" ]; then
                echo -e "${RED}NO TEST:${NC} $f"
                ((count++))
            fi
        done < <(find "$PROJECT_ROOT/frontend/src" -name "*.tsx" -o -name "*.ts" -o -name "*.jsx" -o -name "*.js" 2>/dev/null | grep -v "test\|spec\|__tests__\|node_modules")
    fi

    echo -e "\n${GREEN}Found $count files without tests${NC}"
}

# ── Code Smells Scan ──
scan_smells() {
    separator
    echo -e "${CYAN}[CODE SMELLS]${NC}"
    separator

    # Empty except blocks
    echo -e "${YELLOW}Empty except blocks:${NC}"
    local empty_except=0
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            echo "  $line"
            ((empty_except++))
        fi
    done < <(grep -rn "except.*:" --include="*.py" "$PROJECT_ROOT/app" -A1 2>/dev/null | grep -B1 "pass$\|^\s*$" | grep -v "^--$" || true)
    echo -e "  ${GREEN}Found $empty_except empty except blocks${NC}"

    # Duplicate function names
    echo -e "\n${YELLOW}Duplicate function names:${NC}"
    local dupes=0
    while IFS= read -r name; do
        if [ -n "$name" ]; then
            echo "  Duplicate: $name"
            ((dupes++))
        fi
    done < <(grep -rn "def " --include="*.py" "$PROJECT_ROOT/app" 2>/dev/null | awk -F'def ' '{print $2}' | awk -F'(' '{print $1}' | sort | uniq -d)
    echo -e "  ${GREEN}Found $dupes duplicate function names${NC}"

    # Long functions (>50 lines)
    echo -e "\n${YELLOW}Long functions (>50 lines):${NC}"
    local long_funcs=0
    if command -v python3 &>/dev/null; then
        while IFS= read -r result; do
            if [ -n "$result" ]; then
                echo "  $result"
                ((long_funcs++))
            fi
        done < <(python3 -c "
import ast, sys, os
root = sys.argv[1] if len(sys.argv) > 1 else '.'
for dirpath, _, filenames in os.walk(os.path.join(root, 'app')):
    for fname in filenames:
        if fname.endswith('.py') and fname != '__init__.py':
            fpath = os.path.join(dirpath, fname)
            try:
                tree = ast.parse(open(fpath, encoding='utf-8').read())
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        length = node.end_lineno - node.lineno
                        if length > 50:
                            rel = os.path.relpath(fpath, root)
                            print(f'{rel}:{node.lineno} {node.name} ({length} lines)')
            except: pass
" "$PROJECT_ROOT" 2>/dev/null || true)
    fi
    echo -e "  ${GREEN}Found $long_funcs long functions${NC}"
}

# ── Run ──
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     CODEBASE SCAN — $PROJECT_ROOT     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"

case "$MODE" in
    --all)
        scan_todos
        scan_missing_tests
        scan_smells
        ;;
    --todo)    scan_todos ;;
    --tests)   scan_missing_tests ;;
    --smells)  scan_smells ;;
    *)
        echo "Usage: $0 [project_root] [--all|--todo|--tests|--smells]"
        exit 1
        ;;
esac

separator
echo -e "${GREEN}Scan complete.${NC}"
