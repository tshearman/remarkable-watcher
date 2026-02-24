#!/bin/bash
# Wrapper script for launchd — activates the project virtualenv and runs rm-watch.
# Copy this file to the project root and make it executable before installing
# the LaunchAgent plist.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activate the virtualenv built by `nix develop` / `direnv reload`
source "$SCRIPT_DIR/.venv/bin/activate"

# Add Nix profile binaries (inkscape, etc.) to PATH
export PATH="$HOME/.nix-profile/bin:/nix/var/nix/profiles/default/bin:$PATH"

exec rm-watch "$@"
