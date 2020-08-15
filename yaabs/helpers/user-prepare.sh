#!/usr/bin/env bash

TARGET_USER=$1

if [[ "$USER" != "$TARGET_USER" ]]; then
  sudo -u "$TARGET_USER" "$0" "$TARGET_USER" "$URL"
fi

cat << EOF > $HOME/.profile
#!/usr/bin/env bash

export XDG_CONFIG_HOME=${HOME}/.config
export XDG_DATA_HOME=${HOME}/.local/share
source ${XDG_CONFIG_HOME}/env
source ${XDG_CONFIG_HOME}/shells/profile
EOF

cat << EOF > $HOME/.bashrc
[ -f "\${BASHRC}" ] && . "\${BASHRC}"
EOF

cat << EOF > $HOME/.zshenv
ZDOTDIR=\$HOME/.config/shells
EOF

mkdir -p $HOME/.config/auto
mkdir -p $HOME/.local/bin
mkdir -p $HOME/.local/share

[ ! -d $HOME/.local/share/yaabs ] && git clone https://github.com/richard-hajek/yaabs $HOME/.local/share/yaabs
