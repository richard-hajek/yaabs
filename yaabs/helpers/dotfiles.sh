#!/usr/bin/env bash

TARGET_USER=$1
URL=$2

if [[ "$USER" != "$TARGET_USER" ]]; then
  sudo -u "$TARGET_USER" "$0" "$TARGET_USER" "$URL"
fi

[ -d "$HOME/.config/yaabs" ] && git clone "$URL" "$HOME/.config/yaabs"
cd "$HOME/.config/yaabs" || exit
git pull

for f in "$HOME/.config/yaabs/"*; do

  [[ -L "$HOME/.config/`basename $f`" ]] && continue

  if [[ -d "$HOME/.config/`basename $f`" ]]; then
    echo "==> COLLISION ON ${f}"
    continue
  fi

  ln -s  "$f" "$HOME/.config/`basename $f`"
done