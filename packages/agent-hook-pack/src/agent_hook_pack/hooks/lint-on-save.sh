#!/usr/bin/env bash
# Lint on Save Hook â€” PostToolUse
# Runs linter after Claude writes/edits a file.
# Keep hooks FAST (<5 seconds) or Claude may not wait (V5 lesson).
#
# Based on Claude Code Mastery Guides V1-V5 by TheDecipherist

# Read the tool input from stdin
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

EXTENSION="${FILE_PATH##*.}"

case "$EXTENSION" in
    ts|tsx)
        # TypeScript â€” run type check on the specific file if tsc is available
        if command -v npx &> /dev/null && [ -f "tsconfig.json" ]; then
            npx tsc --noEmit --pretty "$FILE_PATH" 2>&1 | head -20
        fi
        ;;
    js|jsx)
        # JavaScript â€” run eslint if available
        if command -v npx &> /dev/null && [ -f ".eslintrc*" ] || [ -f "eslint.config.*" ]; then
            npx eslint --no-error-on-unmatched-pattern "$FILE_PATH" 2>&1 | head -20
        fi
        ;;
    py)
        # Python â€” run ruff or flake8 if available
        if command -v ruff &> /dev/null; then
            ruff check "$FILE_PATH" 2>&1 | head -20
        elif command -v flake8 &> /dev/null; then
            flake8 "$FILE_PATH" 2>&1 | head -20
        fi
        ;;
    vue)
        # Vue â€” run vue-tsc if available
        if command -v npx &> /dev/null && [ -f "tsconfig.json" ]; then
            npx vue-tsc --noEmit 2>&1 | head -20
        fi
        ;;
    svelte)
        # Svelte â€” run svelte-check if available
        if command -v npx &> /dev/null; then
            npx svelte-check --tsconfig ./tsconfig.json 2>&1 | head -20
        fi
        ;;
    go)
        # Go â€” run go vet if available
        if command -v go &> /dev/null; then
            go vet "$FILE_PATH" 2>&1 | head -20
        fi
        ;;
    rs)
        # Rust â€” run cargo check from nearest Cargo.toml
        CARGO_DIR=$(dirname "$FILE_PATH")
        while [ "$CARGO_DIR" != "/" ] && [ "$CARGO_DIR" != "." ]; do
            if [ -f "$CARGO_DIR/Cargo.toml" ]; then
                (cd "$CARGO_DIR" && cargo check 2>&1 | tail -10)
                break
            fi
            CARGO_DIR=$(dirname "$CARGO_DIR")
        done
        ;;
    lua)
        # Lua â€” run luacheck if available
        if command -v luacheck &> /dev/null; then
            luacheck "$FILE_PATH" --no-color 2>&1 | head -20
        fi
        ;;
esac

exit 0
