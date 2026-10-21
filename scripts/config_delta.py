#!/usr/bin/env python3
"""
config_delta.py - показать, чем конфиг сборки отличается от официального.

Version: 1.0

Смысл: дельта конфига легко ломает ядро незаметно. Один раз снос маской
CONFIG_DEFAULT_* унёс DEFAULT_SECURITY_SELINUX, DEFAULT_MMAP_MIN_ADDR,
DEFAULT_USE_ENERGY_AWARE, DEFAULT_HOSTNAME и DEFAULT_IOSCHED, и ядро перестало
загружаться. Поэтому печатаем различие целиком - до прошивки.

Usage:
    config_delta.py <built.config> <official.config>
"""
import sys

VERSION = "1.0"


def load(path):
    out = {}
    for line in open(path):
        line = line.rstrip('\n')
        if not line or line.startswith('#') and ' is not set' not in line:
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k] = v
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    new, old = load(sys.argv[1]), load(sys.argv[2])
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(new) & set(old) if new[k] != old[k])
    print('config_delta %s: +%d -%d ~%d' % (VERSION, len(added), len(removed), len(changed)))
    for k in added:
        print('  + %s=%s' % (k, new[k]))
    for k in removed:
        print('  - %s=%s' % (k, old[k]))
    for k in changed:
        print('  ~ %s: %s -> %s' % (k, old[k], new[k]))


if __name__ == '__main__':
    main()
