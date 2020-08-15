#!/usr/bin/env sh

mkdir -p "$HOME/.local/share"
mkdir -p "$HOME/.local/bin/"

cd "$HOME/.local/share" || exit
git clone https://github.com/richard-hajek/yaabs

cd yaabs
./yaabs/yaabs.py users sync "./configs/base.json"