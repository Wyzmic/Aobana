#!/bin/bash
RES="$(cd "$(dirname "$0")" && pwd)"
printf '\033]0;露草 / Aobana\007'
clear
cd "$RES/app" || exit 1
exec "$RES/app/python/bin/python3" -m aobana
