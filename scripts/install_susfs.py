#!/usr/bin/env python3
"""
install_susfs.py - включить KernelSU + SUSFS в конфиге ядра.

Version: 1.0

Ставит CONFIG_KSU=y и набор CONFIG_KSU_SUSFS_*. Опции, которых нет
в Kconfig, будут молча отброшены olddefconfig - это ожидаемо.

ВАЖНО про SUS_MAP и OPEN_REDIRECT: в susfs_ksu_compat.h (мост между
SukiSU v4.1.3 и SUSFS v1.5.5) они объявлены как do {} while(0), то
есть заглушки. Включать их нет смысла - менеджер покажет опцию, а
ядро проигнорирует.

Usage:
    install_susfs.py <config_path>
"""
import os
import re
import sys

VERSION = "1.0"

OPTS = {
    "KSU": "y",
    "KSU_FEATURE_ADBROOT": "y",
    "KSU_DEBUG": "n",
    "KSU_SUSFS": "y",
    "KSU_SUSFS_SUS_PATH": "y",
    "KSU_SUSFS_SUS_MOUNT": "y",
    "KSU_SUSFS_SUS_KSTAT": "y",
    "KSU_SUSFS_SUS_OVERLAYFS": "y",
    "KSU_SUSFS_SPOOF_UNAME": "y",
    "KSU_SUSFS_ENABLE_LOG": "n",
    "KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS": "y",
    "KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG": "y",
    "KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT": "y",
    "KSU_SUSFS_TRY_UMOUNT": "y",
    "KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT": "y",
    "KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT": "y",
    # Заглушки в susfs_ksu_compat.h - держим выключенными явно,
    # иначе Kconfig ставит их в y по default.
    "KSU_SUSFS_SUS_MAP": "n",
    "KSU_SUSFS_OPEN_REDIRECT": "n",
}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg = sys.argv[1]
    if not os.path.isfile(cfg):
        sys.exit("install_susfs %s: нет файла %s" % (VERSION, cfg))

    print("install_susfs %s" % VERSION)

    with open(cfg, encoding="utf-8") as f:
        lines = f.read().splitlines()

    out = []
    for line in lines:
        m = re.match(r'^(# )?CONFIG_([A-Z0-9_]+)(=| is not set)', line)
        if m and m.group(2) in OPTS:
            continue
        out.append(line)

    for k, v in OPTS.items():
        out.append("CONFIG_%s=y" % k if v == "y"
                   else "# CONFIG_%s is not set" % k)

    with open(cfg, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    for k in sorted(OPTS):
        print("  %s=%s" % (k, OPTS[k]))


if __name__ == "__main__":
    main()
