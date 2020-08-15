#!/usr/bin/env bash

TARGET_USER=$1

if [[ "$USER" != "$TARGET_USER" ]]; then
  sudo -u "$TARGET_USER" "$0" "$TARGET_USER" "$URL"
fi

mkdir -p $HOME/.config/auto
mkdir -p $HOME/.local/bin
mkdir -p $HOME/.local/share

[ ! -d $HOME/.local/share/yaabs ] && git clone https://github.com/richard-hajek/yaabs $HOME/.local/share/yaabs

cd $HOME/.local/share/yaabs

git pull --ff-only
