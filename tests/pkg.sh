#!/bin/sh
# Smoke-test Orb! project scaffolding, Git dependency commands and vendored module lookup.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ORB="$ROOT/build/orb"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/mockbin" "$TMP/source/src"
cat > "$TMP/source/src/greetings.orb" <<'EOF'
pub fn message() -> str { return "dependency-module-ok"; }
EOF
cat > "$TMP/mockbin/git" <<'EOF'
#!/bin/sh
if [ "$1" = "clone" ]; then
    for last do :; done
    mkdir -p "$last"
    cp -R "$SOURCE_REPO/." "$last/"
    mkdir -p "$last/.git"
    printf '[core]\nrepositoryformatversion = 0\n' > "$last/.git/config"
    exit 0
fi
if [ "$1" = "-C" ] && [ "$3" = "pull" ] && [ "$4" = "--ff-only" ]; then
    exit 0
fi
echo "unexpected mock git invocation: $*" >&2
exit 2
EOF
chmod +x "$TMP/mockbin/git"
export SOURCE_REPO="$TMP/source"
export PATH="$TMP/mockbin:$PATH"
cd "$TMP"
"$ORB" init package-smoke
[ -f orb.toml ] && [ -f main.orb ]
"$ORB" install greetings https://example.invalid/greetings.git
grep -q 'greetings = "https://example.invalid/greetings.git"' orb.toml
"$ORB" install
"$ORB" update
"$ORB" list | grep -q 'greetings.*\[installed\]'
cat > main.orb <<'EOF'
use greetings;
fn main() { println(greetings.message()); }
EOF
"$ORB" run main.orb > output.txt
[ "$(cat output.txt)" = "dependency-module-ok" ]
echo "package manager smoke test: ok"
