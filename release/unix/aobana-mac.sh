#!/bin/bash
CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
RES="$CONTENTS/Resources"
xattr -dr com.apple.quarantine "$(dirname "$CONTENTS")" 2>/dev/null
(cd "$RES/app" && "$RES/app/python/bin/python3" -m aobana --open-only) && exit 0
exec open -a Terminal "$RES/Aobana.command"
