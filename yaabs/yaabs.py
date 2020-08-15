#!/usr/bin/env python3
import os
import json
import subprocess
import shutil
import argparse
from collections import defaultdict
import filecmp

from sys import *

PACMAN_CACHE = "/usr/cache/pacman/pkg"
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


dry_run = True


def c(command):
    print(f"Running \"{command}\"")

    if dry_run:
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


def cache_package(package):
    c(f"mkdir -p {CACHE_ROOT}")
    c(f"rm -rf {CACHE_ROOT}/*")
    c(f"rm -rf {CACHE_ROOT}/.*")
    c(f"tar xf {PACMAN_CACHE}/{package} --directory {CACHE_ROOT}")


def diff_package(package):
    diffs = filecmp.dircmp(f"{CACHE_ROOT}", "/", ignore=DIFF_IGNORE)


def process_config_sync(cfg):
    def systemd_service_enable(_, service):
        c(f"systemctl enable {service}")

    def config_editor(file, commands):
        for command in commands:
            c(f"{command} {file}")

    config_processors = defaultdict(lambda: config_editor, {"service-enable": systemd_service_enable})

    for package in cfg[SECTIONS.Configuration]:
        cache_package(package)
        for setting in cfg[SECTIONS.Configuration][package]:
            config_processors[setting](setting, cfg[SECTIONS.Configuration][package][setting])


def process_config_diff(cfg):
    print("Not yet implemented")

    print("==> Preparing template, please wait")

    def chroot_install(root, packages, cfg):
        if os.path.isdir(root): shutil.rmtree(root)
        os.makedirs(f"{root}/var/cache/pacman")
        os.symlink(f"/var/cache/pacman/pkg", f"{root}/var/cache/pacman/pkg2")
        c(f"pacstrap {root} {str.join(' ', packages)} --cachedir={root}/var/cache/pacman/pkg2")

    def chroot_diff(chroot, packages, cfg):

        IGNORE = ["passwd", "shadow"]

        print("===> SEARCHING FOR DIFFERENCES")
        for root, directories, filenames in os.walk(f'{chroot}/etc'):
            original = root.replace(f"{chroot}/etc/", "/etc/")
            # print(f"Checking {original} vs {root}... ", end="")

            if not os.path.isdir(original):
                print(f"{original}: Dir missing")
                continue

            diffs = filecmp.dircmp(original, root, ignore=IGNORE)

            if len(diffs.diff_files) != 0:
                print(f"{original}: {diffs.diff_files}")

    nonaur = get_templat2e_packages(cfg, False)
    chroot_install("/var/cache/yaabs", nonaur, cfg)
    chroot_diff("/var/cache/yaabs", nonaur, cfg)


def process_users_sync(cfg):
    home = defaultdict(lambda: f"/home/{user}", {"root": "/root"})

    def prepare(user):
        c(f"useradd -m {user}")
        c(f"sudo -u {user} mkdir -p {home[user]}/.config/environment")

        [c(f"sudo -u {user} touch {file}") for file in
         [f"{home[user]}/.profile", f"{home[user]}/.config/environment/auto",
          f"{home[user]}/.config/environment/profile"]]

        dot_profile = [
            "export XDG_CONFIG_HOME=${HOME}/.config",
            "export XDG_DATA_HOME=${HOME}/.local/share",
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
            c(f"sudo -u {user} {command}")

    def environment(user, _, vars):
        for var in vars:
            c(f"echo {var}=\"{vars[var]}\" >> {home[user]}/.config/environment/auto")

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


def process_aur_sync(cfg):
    print("Not yet implemented")

    def aur_installer(field, packages):
        c("useradd -m build")
        c("cp ./aurhelper.sh /home/build")

        for aur_package in str.split(packages, ' '):
            code = c(f"sudo -u build /home/build/aurhelper.sh {aur_package}")
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
    args = parser.parse_args()
    args.configs = args.configs[0]

    dry_run = args.dry

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
