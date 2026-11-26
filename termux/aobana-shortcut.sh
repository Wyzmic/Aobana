#!/data/data/com.termux/files/usr/bin/bash
#   AOBANA_BROWSER=<package>   the browser to open (default Firefox, where Yomitan works);
#                              when it is not installed, the default browser opens instead
source /data/data/com.termux/files/usr/etc/profile

main() {
AOBANA_DIR="${AOBANA_DIR:-/storage/emulated/0/Aobana}"
DISTRO="aobana"
BROWSER_PKG="${AOBANA_BROWSER:-org.mozilla.firefox}"
INSTALL_URL="https://raw.githubusercontent.com/Wyzmic/Aobana/main/termux/install.sh"
UPDATE_EXIT_CODE=75

PORT="$AOBANA_PORT"
CONFIG="$AOBANA_DIR/data/config.json"
if [ -z "$PORT" ] && [ -f "$CONFIG" ]; then
    PORT=$(sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$CONFIG" | head -n 1)
fi
PORT="${PORT:-5000}"
URL="http://127.0.0.1:$PORT/"
APP_ID="aobana"

up() { (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; }

target() {
    local at=""
    [ -f "$AOBANA_DIR/data/kept-tab" ] && at="$(head -n 1 "$AOBANA_DIR/data/kept-tab" 2>/dev/null)"
    case "$at" in
        //*|*[[:space:]\'\"\\]*) at="/" ;;
        /*) ;;
        *) at="/" ;;
    esac
    printf '%s%s' "${URL%/}" "$at"
}
page_shown() { curl -fsS --max-time 2 "${URL}api/update" 2>/dev/null | grep -Eq '"page_shown": ?true'; }
open_page() {
    local to
    to="$(target)"
    if am start -a android.intent.action.VIEW -d "$to" -p "$BROWSER_PKG" \
        --es com.android.browser.application_id "$APP_ID" 2>&1 | grep -qi "error"; then
        termux-open-url "$to"
    fi
    for _ in $(seq 1 16); do
        if page_shown; then
            echo "Aobana is on screen."
            return 0
        fi
        sleep 0.5
    done
    echo "No Aobana page on screen after 8 s: switch to the browser."
}

quit_termux() {
    local app
    app=$(pidof com.termux 2>/dev/null | awk '{print $1}')
    [ -n "$app" ] || return 0
    [ "$(ps -A -o ppid= 2>/dev/null | awk -v p="$app" '$1 == p' | wc -l)" -le 1 ] || return 0
    am startservice -a com.termux.service_stop -n com.termux/.app.TermuxService >/dev/null 2>&1
}

if up; then
    open_page
    return 0
fi

stop_server() {
    curl -fsS -m 3 -X POST -H 'X-Aobana: 1' -H 'Content-Type: application/json' -d '{}' \
        "http://127.0.0.1:$PORT/api/quit" >/dev/null 2>&1 || { [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null; }
    exit 130
}
trap stop_server INT TERM HUP

first=1
while :; do
    proot-distro login "$DISTRO" -- env AOBANA_TERMUX=1 AOBANA_UPDATER=1 PYTHONPATH="$AOBANA_DIR" \
        python3 -m aobana.server.app &
    PID=$!

    for _ in $(seq 1 120); do
        up && break
        kill -0 "$PID" 2>/dev/null || break
        sleep 0.5
    done
    if up; then
        [ "$first" = 1 ] && open_page
    elif kill -0 "$PID" 2>/dev/null; then
        echo "The server did not answer on port $PORT."
    fi
    first=0

    wait "$PID"
    code=$?
    if [ "$code" != "$UPDATE_EXIT_CODE" ]; then
        [ "$code" = 0 ] || echo "The server stopped; see the messages above."
        [ "$code" = 0 ] && quit_termux
        return "$code"
    fi
    printf '\n== Updating Aobana\n'
    if ! curl -fsSL "$INSTALL_URL" | AOBANA_DIR="$AOBANA_DIR" bash; then
        echo "The update did not finish (see above); starting the version that is installed."
    fi
done
}

main "$@"; exit
