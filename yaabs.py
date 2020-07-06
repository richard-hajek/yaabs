#!/usr/bin/env python3
import os
import json
import subprocess
import shutil
import argparse
from collections import defaultdict

from sys import *


class SECTIONS:
    All = "all"
    Include = "include"
    System = "system"
    Configuration = "configuration"
    Users = "users"


class ACTIONS:
    Install = "install"
    Diff = "diff"


dry_run = True


def call(command):
    print(f"Running \"{command}\"")

    if dry_run:
        return 0

    return os.system(command)


def get_template_packages(cfg, aur=True):
    template = []
    for field in cfg[SECTIONS.System]:
        if str.startswith(field, "packages") or (field == "aur" and aur):
            template += str.split(cfg["system"][field], ' ')

    groups = str.split(subprocess.check_output(['pacman', '-Sgq']).decode('utf-8'), '\n')
    groups = list(filter(None, groups))

    for package in template:
        if package in groups:
            template.remove(package)
            template += str.split(subprocess.check_output(['pacman', '-Sgq', package]).decode('utf-8'), '\n')

    template = set(template)

    if "include" not in cfg:
        return template

    for include in cfg["include"]:
        with open(include, 'r') as cfgFile:
            include_cfg = json.loads(str.join('\n', cfgFile.readlines()))
        template |= get_template_packages(include_cfg)

    return template


def process_system_install(cfg):
    def abort():
        print("Command seems to have failed! Aborting...")
        exit(1)

    def ok():
        pass

    return_responses = defaultdict(lambda: abort, {0: ok})

    def package_installer(field, packages):
        if not str.startswith(field, "packages"):
            return

        code = call(f"pacman -S --needed --noconfirm {packages}")
        return_responses[code]()

    def aur_installer(field, packages):
        call("useradd -m build")
        call("cp ./aurhelper.sh /home/build")

        for aur_package in str.split(packages, ' '):
            code = call(f"sudo -u build /home/build/aurhelper.sh {aur_package}")
            return_responses[code]()
            code = call(f"pacman -U --needed --noconfirm /home/build/{aur_package}/*.pkg.tar.xz")
            return_responses[code]()

        call("userdel build -r")

    package_processors = defaultdict(lambda: package_installer, {"aur": aur_installer})

    for field in cfg[SECTIONS.System]:
        package_processors[field](field, cfg[SECTIONS.System][field])


def process_system_diff(cfg):
    get_installed_packages = lambda: set(str.split(subprocess.check_output(['pacman', '-Qq']).decode('utf-8'), '\n'))
    get_end_packages = lambda: set(str.split(subprocess.check_output(['pacman', '-Qqet']).decode('utf-8'), '\n'))

    system = get_installed_packages()
    template = get_template_packages(cfg)
    end = get_end_packages()

    print("===>Template:")
    print(str.join(' ', template))

    print("===>Missing packages:")
    print(str.join(' ', template - system))

    print("===>Packages not in template:")
    print(str.join(' ', end - template))


def process_config_install(cfg):
    def systemd_service_enable(_, service):
        call(f"systemd enable {service}")

    def config_editor(file, commands):
        for command in commands:
            call(f"{command} {file}")

    config_processors = defaultdict(lambda: config_editor, {"service-enable": systemd_service_enable})

    for package in cfg[SECTIONS.Configuration]:
        for setting in cfg[SECTIONS.Configuration][package]:
            config_processors[setting](setting, cfg[SECTIONS.Configuration][package][setting])


def process_config_diff(cfg):
    print("Not yet implemented")


def process_users_install(cfg):

    home = defaultdict(lambda: f"/home/{user}", {"root": "/root"})

    def prepare(user):
        call(f"useradd -m {user}")
        call(f"sudo -u {user} mkdir -p {home[user]}/.config/environment")

        [call(f"sudo -u touch {file}") for file in
         [f"{home[user]}/.profile", f"{home[user]}/.config/environment/auto",
          f"{home[user]}/.config/environment/profile"]]

        dot_profile = [
                "#!/bin/sh",
                "",
                "export XDG_CONFIG_HOME=\"$HOME/.config\"",
                "export XDG_DATA_HOME=\"$HOME/.local/share\"",
                "source ${XDG_CONFIG_HOME}/environment/auto",
                "source ${XDG_CONFIG_HOME}/environment/profile"
            ]

        if dry_run:
            print(f"{home[user]}/.profile would now be generated as {dot_profile}")
            return
        with open(f"{home[user]}/.profile", 'w') as f:
            f.writelines(dot_profile)

    def setup(user, _, commands):
        for command in commands:
            call(f"sudo -u {user} {command}")

    def environment(user, _, vars):
        for var in vars:
            call(f"echo {var}=\"{vars[var]}\" >> {home[user]}/.config/environment/auto")

    def not_found(user, property, _):
        print(f"Invalid user property {property} in user {user}")
        exit(1)


    setuppers = defaultdict(lambda: not_found, {"setup": setup, "environment": environment})

    for user in cfg[SECTIONS.Users]:
        prepare(user)
        for property in cfg[SECTIONS.Users][user]:
            setuppers[property](user, property, cfg[SECTIONS.Users][user][property])


def process_users_diff(cfg):
    print("Not yet implemented")


# forgive me god for the following lines
def process_system(cfg, action):
    {ACTIONS.Install: process_system_install, ACTIONS.Diff: process_system_diff}[action](cfg)


def process_config(cfg, action):
    {ACTIONS.Install: process_config_install, ACTIONS.Diff: process_config_diff}[action](cfg)


def process_users(cfg, action):
    {ACTIONS.Install: process_users_install, ACTIONS.Diff: process_users_diff}[action](cfg)


def read_config(cli_args):
    with open(cli_args.configs[0]) as f:
        cfg = json.load(f)

    cfg.setdefault(SECTIONS.Include, [])
    cfg.setdefault(SECTIONS.System, {})
    cfg.setdefault(SECTIONS.Configuration, {})
    cfg.setdefault(SECTIONS.Users, {})

    for configs in cli_args.configs[1:]:
        cfg["include"] += configs

    return cfg


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='yaabs')
    parser.add_argument('section', type=str,
                        choices=[SECTIONS.All, SECTIONS.System, SECTIONS.Configuration, SECTIONS.Users])
    parser.add_argument('action', type=str, choices=[ACTIONS.Install, ACTIONS.Diff])
    parser.add_argument('configs', action='append', nargs='+')
    parser.add_argument('-d', '--dry', action='store_true', help='Dry run')
    args = parser.parse_args()
    args.configs = args.configs[0]

    dry_run = args.dry

    config = read_config(args)

    sections_calls = {SECTIONS.All: [process_system, process_config, process_users],
                      SECTIONS.System: [process_system],
                      SECTIONS.Configuration: [process_config],
                      SECTIONS.Users: [process_users]}

    for section in sections_calls[args.section]:
        section(config, args.action)
