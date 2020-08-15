#!/usr/bin/env sh

set -e # Exit on command failure

cd /home/build || exit 1
git clone https://aur.archlinux.org/"$1"
cd "$1" || exit 1
makepkg -s
