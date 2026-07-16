#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# view_map.sh
# ─────────────────────────────────────────────────────────────────────────────
# Opens the saved PGM map using the system's default desktop file handler.
# ─────────────────────────────────────────────────────────────────────────────

echo "Opening map ~/maps/stage4/map.pgm..."
xdg-open ~/maps/stage4/map.pgm >/dev/null 2>&1 &
echo "Done!"
