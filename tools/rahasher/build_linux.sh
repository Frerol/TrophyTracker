#!/usr/bin/env bash
# Build RAHasher for Linux (x86_64) from the official RALibretro source, with
# CHD support, and place it in tools/rahasher/. See RAHasher-SOURCE.txt.
#
# Build releases on the oldest supported platform (Ubuntu 22.04, glibc 2.35):
# the binary requires the glibc of the machine it was built on.
set -euo pipefail
TAG="${RAHASHER_TAG:-1.8.3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --quiet --branch "$TAG" --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/RetroAchievements/RALibretro.git "$WORK/RALibretro"
cd "$WORK/RALibretro"
# HAVE_CHD makes .chd images hashable, as in the official Windows build.
# HAVE_UNISTD_H lets the bundled zlib build with GCC 14+, which rejects the
# implicit read/close/lseek declarations it otherwise relies on.
make -f Makefile.RAHasher HAVE_CHD=1 CC="gcc -DHAVE_UNISTD_H"
strip bin64/RAHasher
install -m 0755 bin64/RAHasher "$HERE/RAHasher"
sha256sum "$HERE/RAHasher"
