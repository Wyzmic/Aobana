#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
PY="$HERE/app/python/bin/python3"
SELF="${APPIMAGE:-$HERE/aobana}"
cd "$HERE/app" || exit 1

"$PY" -m aobana --open-only && exit 0

if [ -t 1 ] || [ -n "$AOBANA_NO_TERMINAL" ]; then
    case "$(ps -o comm= -p "$PPID" 2>/dev/null)" in
        bash|zsh|fish|sh|dash|ksh|mksh|tcsh|csh|nu|xonsh) ;;
        *) export AOBANA_APP_WINDOW=1 ;;
    esac
    exec "$PY" -m aobana
fi

export AOBANA_NO_TERMINAL=1
for t in x-terminal-emulator ptyxis gnome-terminal konsole xfce4-terminal mate-terminal kitty alacritty wezterm foot xterm; do
    command -v "$t" >/dev/null 2>&1 || continue
    case "$t" in
        ptyxis)          exec "$t" --new-window -- "$SELF" ;;
        gnome-terminal)  exec "$t" -- "$SELF" ;;
        xfce4-terminal)  exec "$t" -x "$SELF" ;;
        mate-terminal)   exec "$t" -x "$SELF" ;;
        wezterm)         exec "$t" start -- "$SELF" ;;
        kitty|foot)      exec "$t" "$SELF" ;;
        *)               exec "$t" -e "$SELF" ;;
    esac
done
exec "$PY" -m aobana
