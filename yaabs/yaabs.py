#!/usr/bin/env python3

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import getpass
from collections import defaultdict
from sys import *

PACMAN_CACHE = "/var/cache/pacman/pkg"
CACHE_ROOT = "/tmp/yaabs"
DIFF_IGNORE = [".BUILDINFO", ".PKGINFO", ".MTREE"]


class SECTIONS:
    All = "all"
    Include = "include"
    Packages = "packages"
    AUR = "aur"
    Configuration = "configuration"
    Users = "users"


class ACTIONS:
    Sync = "sync"
    Diff = "diff"


HELPERS_LOCATION = os.path.dirname(os.path.realpath(__file__)) + "/helpers/"
HELPERS = {
    "aur": HELPERS_LOCATION + "aur.sh",
    "user-prepare": HELPERS_LOCATION + "user-prepare.sh",
    "dotfiles": HELPERS_LOCATION + "dotfiles.sh"
}

dry_run = False
verbose = False


# region Utils

def c(command, force_run=False):
    if verbose:
        print(f"Running \"{command}\"")

    if dry_run and not force_run:
        return 0

    return os.system(command)


def get_template_packages(cfg, aur=False):
    packages = []
    pkg_list = cfg[SECTIONS.Packages] if not aur else cfg[SECTIONS.AUR]
    for field in pkg_list:
        if str.startswith(field, "packages"):
            packages += str.split(cfg[SECTIONS.Packages if not aur else SECTIONS.AUR][field], ' ')

    groups = str.split(subprocess.check_output(['pacman', '-Sgq']).decode('utf-8'), '\n')
    groups = list(filter(None, groups))

    for package in packages:
        if package in groups:
            packages.remove(package)
            packages += str.split(subprocess.check_output(['pacman', '-Sgq', package]).decode('utf-8'), '\n')

    packages = set(packages)

    if "include" not in cfg:
        return packages

    for include in cfg["include"]:
        with open(include, 'r') as cfgFile:
            include_cfg = json.loads(str.join('\n', cfgFile.readlines()))
        packages |= get_template_packages(include_cfg, aur=aur)

    return packages


# endregion

# region Packages

def process_package_sync(cfg):
    for field in cfg[SECTIONS.Packages]:
        c(f"pacman -S --needed --noconfirm {cfg[SECTIONS.Packages][field]}")


def process_package_diff(cfg):
    get_installed_packages = lambda: set(str.split(subprocess.check_output(['pacman', '-Qqn']).decode('utf-8'), '\n'))
    get_end_packages = lambda: set(str.split(subprocess.check_output(['pacman', '-Qqetn']).decode('utf-8'), '\n'))

    system = get_installed_packages()
    template = get_template_packages(cfg, False)
    end = get_end_packages()

    print("Template:\t", end='')
    print(str.join(' ', template))

    print("Missing packages:\t", end='')
    print(str.join(' ', template - system))

    print("Packages not in template:\t", end='')
    print(str.join(' ', end - template))


# endregion

# region System Configuration

def systemd_service_enable(_, service, __):
    c(f"systemctl enable {service}")


def config_editor(file, commands, prefix):
    for command in commands:
        c(f"{command} {prefix}/{file}")


CONFIG_SPECIAL_ACTIONS = {"service-enable": systemd_service_enable}
CONFIG_PROCESSORS = defaultdict(lambda: config_editor, CONFIG_SPECIAL_ACTIONS)


def cache_package(package):
    c(f"mkdir -p {CACHE_ROOT}", force_run=True)
    c(f"rm -rf {CACHE_ROOT}/* 2> /dev/null", force_run=True)
    c(f"rm -rf {CACHE_ROOT}/.* 2> /dev/null", force_run=True)
    c(f"tar xf {PACMAN_CACHE}/{package}-[0-9]* --directory {CACHE_ROOT}", force_run=True)


def apply_special_changes(package, cfg, root="/"):
    for setting in cfg[SECTIONS.Configuration][package]:
        if setting not in CONFIG_SPECIAL_ACTIONS:
            continue
        CONFIG_PROCESSORS[setting](setting, cfg[SECTIONS.Configuration][package][setting], root)


def apply_changes(package, cfg, root="/"):
    for setting in cfg[SECTIONS.Configuration][package]:
        if setting in CONFIG_SPECIAL_ACTIONS:
            continue
        CONFIG_PROCESSORS[setting](setting, cfg[SECTIONS.Configuration][package][setting], root)


def diff_cache():
    df = []
    for root, directories, filenames in os.walk(f'{CACHE_ROOT}/etc'):
        original = root.replace(f"{CACHE_ROOT}", "")

        if not os.path.isdir(original):
            if verbose:
                print(f"{original}: Dir missing")

            continue

        diffs = filecmp.dircmp(original, root, ignore=DIFF_IGNORE)

        for f in diffs.diff_files:
            df += [f"{original}/{f}"]

    return df


def process_config_sync(cfg, diff_mode=False):
    if diff_mode:
        print("==>Package differences:")

    for package in cfg[SECTIONS.Configuration]:
        cache_package(package)
        apply_changes(package, cfg, root=CACHE_ROOT)
        susfiles = set(diff_cache())

        if diff_mode:
            if susfiles.__len__() > 0:
                print(f"{package}: {' '.join(list(susfiles))} are different")
            continue

        susfiles |= set(cfg[SECTIONS.Configuration][package].keys()) - set(CONFIG_SPECIAL_ACTIONS.keys())

        for f in susfiles:

            if verbose:
                print(f"Copying {CACHE_ROOT}/{f} to {f}")

            if dry_run:
                continue

            shutil.copy(f"{CACHE_ROOT}/{f}", f"{f}")

        apply_special_changes(package, cfg)


def process_config_diff(cfg):
    process_config_sync(cfg, diff_mode=True)


# endregion

def process_users_sync(cfg):
    home = defaultdict(lambda: f"/home/{user}", {"root": "/root"})

    def prepare(user):
        c(HELPERS["user-prepare"] + f" {user}")

    def setup(user, _, commands):
        for command in commands:
            c(f"sudo -u {user} {command}")

    def environment(user, _, vars):
        c(f"echo > {home[user]}/.config/env")
        for var in vars:
            c(f"echo export {var}=\'{vars[var]}\' >> {home[user]}/.config/env")

    def dotfiles(user, _, values):
        c(HELPERS["dotfiles"] + f" dotfiles \"{user}\" \"{values['upstream']}\" \"{values['prefix']}\"")
    
    def scripts(user, _, values):
        c(HELPERS["dotfiles"] + f" scripts \"{user}\" \"{values['upstream']}\" \"{values['prefix']}\"")
    
    def homef(user, _, values):
        c(HELPERS["dotfiles"] + f" home \"{user}\" \"{values['upstream']}\" \"{values['prefix']}\"")

    def not_found(user, property, _):
        print(f"Invalid user property {property} in user {user}")
        exit(1)

    funcs = defaultdict(lambda: not_found, {"setup": setup, "environment": environment, "dotfiles": dotfiles, "scripts": scripts, "home": homef})

    for user in cfg[SECTIONS.Users]:

        if user != getpass.getuser() and getpass.getuser() != "root":
            continue

        prepare(user)
        for property in cfg[SECTIONS.Users][user]:
            funcs[property](user, property, cfg[SECTIONS.Users][user][property])


def process_users_diff(cfg):
    print("Not yet implemented")


def process_aur_sync(cfg):
    print("Not yet implemented")

    def aur_installer(field, packages):
        c("useradd -m build")
        c("cp ./aur.sh /home/build")

        for aur_package in str.split(packages, ' '):
            code = c(f"sudo -u build /home/build/aur.sh {aur_package}")
            return_responses[code]()
            code = c(f"pacman -U --needed --noconfirm /home/build/{aur_package}/*.pkg.tar.xz")
            return_responses[code]()

        c("userdel build -r")

    package_processors = defaultdict(lambda: package_installer, {"aur": aur_installer})

    for field in cfg[SECTIONS.Packages]:
        package_processors[field](field, cfg[SECTIONS.Packages][field])


def process_aur_diff(cfg):
    print("Not yet implemented")


def read_config(cli_args):
    with open(cli_args.configs[0]) as f:
        cfg = json.load(f)

    cfg.setdefault(SECTIONS.Include, [])
    cfg.setdefault(SECTIONS.Packages, {})
    cfg.setdefault(SECTIONS.Configuration, {})
    cfg.setdefault(SECTIONS.Users, {})

    cfg["include"] = []
    for configs in cli_args.configs[1:]:
        cfg["include"] += [configs]

    return cfg


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='yaabs')
    parser.add_argument('section', type=str,
                        choices=[SECTIONS.All, SECTIONS.Packages, SECTIONS.AUR, SECTIONS.Configuration, SECTIONS.Users])
    parser.add_argument('action', type=str, choices=[ACTIONS.Sync, ACTIONS.Diff])
    parser.add_argument('configs', action='append', nargs='+')
    parser.add_argument('-d', '--dry', action='store_true', help='Dry run')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose')
    args = parser.parse_args()
    args.configs = args.configs[0]

    dry_run = args.dry
    verbose = args.verbose

    config = read_config(args)


    # forgive me god for the following lines
    def process_system(cfg, action):
        {ACTIONS.Sync: process_package_sync, ACTIONS.Diff: process_package_diff}[action](cfg)


    def process_config(cfg, action):
        {ACTIONS.Sync: process_config_sync, ACTIONS.Diff: process_config_diff}[action](cfg)


    def process_users(cfg, action):
        {ACTIONS.Sync: process_users_sync, ACTIONS.Diff: process_users_diff}[action](cfg)


    def process_aur(cfg, action):
        {ACTIONS.Sync: process_aur_sync, ACTIONS.Diff: process_aur_diff}[action](cfg)


    sections_calls = {SECTIONS.All: [process_system, process_config, process_users],
                      SECTIONS.Packages: [process_system],
                      SECTIONS.AUR: [process_aur],
                      SECTIONS.Configuration: [process_config],
                      SECTIONS.Users: [process_users]}

    for section in sections_calls[args.section]:
        section(config, args.action)
