#!/usr/bin/env bash

MODE=$1
TARGET_USER=$2
UPSTREAM=$3
PREFIX=$4

if [[ "$USER" != "$TARGET_USER" ]]; then
  sudo -u "$TARGET_USER" "$0" "$@"
fi

repo=`basename $UPSTREAM .git`

[ ! -d "$HOME/.config/yaabs" ] && mkdir -p "$HOME/.config/yaabs"

cd "$HOME/.config/yaabs"

[ ! -d "$HOME/.config/yaabs/$repo" ] && git clone $UPSTREAM

cd "$HOME/.config/yaabs/$repo" || exit

git pull -s resolve

TARGET=

case $MODE in
	"dotfiles")
		TARGET="$HOME/.config"
		;;
	"scripts")
		TARGET="$HOME/.local/bin"
		;;
	"home")
		TARGET="$HOME"
		;;
esac

for f in "$HOME/.config/yaabs/$repo/$PREFIX/"*; do
  echo Processing file $f

  [[ -L "$TARGET/`basename $f`" ]] && continue

  if [[ -d "$TARGET/`basename $f`" ]]; then
    echo "==> COLLISION ON ${f}"
    mkdir -p "$HOME/collisions"
    mv "$TARGET/`basename $f`" "$HOME/collisions"
  fi

  ln -s  "$f" "$TARGET/`basename $f`"
done
