#!/usr/bin/env bash
# Install Flipper Cursor Buddy hooks into the repository .cursor/hooks.json.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/flipper-cursor-buddy"
HOOKS_SRC="$PLUGIN_DIR/.cursor/hooks.json"
HOOKS_DST="$REPO_ROOT/.cursor/hooks.json"

if [ ! -f "$HOOKS_SRC" ]; then
  echo "Missing $HOOKS_SRC" >&2
  exit 1
fi

mkdir -p "$REPO_ROOT/.cursor"

if [ ! -f "$HOOKS_DST" ]; then
  cp "$HOOKS_SRC" "$HOOKS_DST"
  echo "Installed hooks to $HOOKS_DST"
  exit 0
fi

python3 - "$HOOKS_DST" "$HOOKS_SRC" <<'PY'
import json
import sys
from pathlib import Path

dst_path = Path(sys.argv[1])
src_path = Path(sys.argv[2])

dst = json.loads(dst_path.read_text(encoding="utf-8"))
src = json.loads(src_path.read_text(encoding="utf-8"))

dst.setdefault("version", 1)
dst_hooks = dst.setdefault("hooks", {})
src_hooks = src.get("hooks", {})

for event, entries in src_hooks.items():
    existing = dst_hooks.get(event, [])
    src_cmds = {entry.get("command") for entry in entries}
    merged = [entry for entry in existing if entry.get("command") not in src_cmds]
    merged.extend(entries)
    dst_hooks[event] = merged

dst_path.write_text(json.dumps(dst, indent=2) + "\n", encoding="utf-8")
print(f"Merged Flipper hooks into {dst_path}")
PY

echo ""
echo "Next steps:"
echo "  1. Open Cursor Settings → Hooks and confirm hooks are loaded"
echo "  2. Trust this workspace if prompted"
echo "  3. Start a new agent session"
echo "  4. Use: flipper-cursor-buddy/bin/flipper-bridge status"
