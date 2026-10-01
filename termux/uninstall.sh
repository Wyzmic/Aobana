#!/data/data/com.termux/files/usr/bin/bash
# 露草 / Aobana on Android: uninstall, in one command, from Termux.
#
#   curl -fsSL https://raw.githubusercontent.com/Wyzmic/Aobana/main/termux/uninstall.sh | bash
#
#   AOBANA_DIR=<folder>   the folder install.sh used (default /storage/emulated/0/Aobana)
AOBANA_DIR="${AOBANA_DIR:-/storage/emulated/0/Aobana}"
DISTRO="aobana"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
PD_DIR="$PREFIX/var/lib/proot-distro"
PHONE_FILES="aobana requirements.txt LICENSE THIRD_PARTY_NOTICES.md CHANGELOG.md data/ruby static"
OLD_ROOT_FILES="app.py engine.py utils.py paths.py library.py analyser.py indexer.py epub_indexer.py
manga_indexer.py ass_ruby.py folder_picker.py updater.py index.html __pycache__"
OLD_CLONE_FILES=".git .gitattributes .gitignore assets release termux Aobana.bat aobana.sh
launcher.py README.md README.ja.md"

say() { printf '\n== %s\n' "$1"; }

say "Stopping Aobana"
pkill -f "[p]root-distro login $DISTRO" 2>/dev/null
sleep 1
echo "done"

say "Aobana's Ubuntu"
if [ -d "$PD_DIR/containers/$DISTRO/rootfs" ] && command -v proot-distro >/dev/null; then
    proot-distro remove "$DISTRO"
fi
for d in "$PD_DIR/containers/$DISTRO" "$PD_DIR/installed-rootfs/$DISTRO"; do
    if [ -e "$d" ]; then
        chmod -R u+rwx "$d" 2>/dev/null
        rm -rf "$d"
    fi
done
echo "removed"

say "Home-screen shortcut"
rm -f "$HOME/.shortcuts/Aobana"
echo "removed"

say "App files in $AOBANA_DIR"
if [ -d "$AOBANA_DIR" ]; then
    for f in $PHONE_FILES $OLD_ROOT_FILES $OLD_CLONE_FILES; do rm -rf "${AOBANA_DIR:?}/$f"; done
    rmdir "$AOBANA_DIR/data" 2>/dev/null
    if rmdir "$AOBANA_DIR" 2>/dev/null; then
        echo "removed (nothing of yours was in it, so the folder went too)"
    else
        echo "removed; kept: $(ls -A "$AOBANA_DIR" | tr '\n' ' ')"
    fi
else
    echo "not there"
fi

say "proot-distro"
others="$(ls -A "$PD_DIR/containers" "$PD_DIR/installed-rootfs" 2>/dev/null | grep -v -e '^$' -e ':$')"
if [ -z "$others" ]; then
    rm -rf "$PD_DIR"
    if dpkg -s proot-distro >/dev/null 2>&1; then
        pkg uninstall -y proot-distro
    fi
    apt-get autoremove -y
else
    echo "kept: other containers use it ($(echo $others))"
fi

cat <<EOF

Aobana is uninstalled.
Your databases, media and settings in $AOBANA_DIR (if there were any) were kept;
delete them with a file manager if you no longer want them.
EOF
