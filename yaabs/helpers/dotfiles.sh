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

git pull --rebase

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

shopt -s nullglob
shopt -s dotglob

for f in "$HOME/.config/yaabs/$repo/$PREFIX/"*; do
  echo Processing file $f
  TARGETF="$TARGET/`basename $f`"
  BASEF="`basename $f`"

  [[ -L "$TARGETF" ]] && continue

  if [[ -d "$TARGETF" || -f "$TARGETF" ]]; then
    echo -n "==> COLLISION ON ${f} "
    mkdir -p "$HOME/collisions"
    POSTFIX=1

    while [[ -f "$HOME/collisions/${BASEF}${POSTFIX}" ]]; do
    	(( POSTFIX ++ ))
    done

    echo "Archiving as $HOME/collisions/${BASEF}${POSTFIX}"

    mv "$TARGETF" "$HOME/collisions/${BASEF}${POSTFIX}"
  fi

  ln -s  "$f" "$TARGETF"
done
