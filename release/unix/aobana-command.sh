#!/bin/bash
RES="$(cd "$(dirname "$0")" && pwd)"
printf '\033]0;露草 / Aobana\007'
clear
cd "$RES/app" || exit 1
export AOBANA_APP_WINDOW=1
"$RES/app/python/bin/python3" -m aobana
code=$?
if [ "$code" -eq 0 ]; then
    TTY_NAME="$(tty)"
    ( sleep 1; osascript -e 'on run {t}' -e 'tell application "Terminal"' \
        -e 'close (every window whose tty is t)' -e 'delay 0.5' -e 'if (count windows) is 0 then quit' \
        -e 'end tell' -e 'end run' "$TTY_NAME" ) </dev/null >/dev/null 2>&1 &
    disown
fi
exit "$code"
