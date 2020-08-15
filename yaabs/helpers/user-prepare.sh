#!/usr/bin/env bash

TARGET_USER=$1

if [[ "$USER" != "$TARGET_USER" ]]; then
  sudo -u "$TARGET_USER" "$0" "$TARGET_USER" "$URL"
fi

cat << EOF >> $HOME/.profile
export XDG_CONFIG_HOME=${HOME}/.config
export XDG_DATA_HOME=${HOME}/.local/share
source ${XDG_CONFIG_HOME}/auto/variables
source ${XDG_CONFIG_HOME}/environment/profile
EOF

mkdir -p $HOME/.config/auto
mkdir -p $HOME/.local/bin
mkdir -p $HOME/.local/share

[ ! -d $HOME/.local/share/yaabs ] && git clone https://github.com/richard-hajek/yaabs $HOME/.local/share/yaabs