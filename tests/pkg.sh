#!/bin/sh
# Smoke-test Orb! project scaffolding and vendored Git-package module lookup.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ORB="$ROOT/build/orb"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
cd "$TMP"
"$ORB" init package-smoke
[ -f orb.toml ] && [ -f main.orb ]
"$ORB" install | grep -q "no dependencies declared"
"$ORB" update
"$ORB" list | grep -q "no dependencies declared"
mkdir -p .orb/packages/greetings/src
cat > .orb/packages/greetings/src/greetings.orb <<'EOF'
pub fn message() -> str { return "dependency-module-ok"; }
EOF
cat > main.orb <<'EOF'
use greetings;
fn main() { println(greetings.message()); }
EOF
"$ORB" run main.orb > output.txt
[ "$(cat output.txt)" = "dependency-module-ok" ]
"$ORB" list | grep -q "no dependencies declared"
echo "package manager smoke test: ok"
