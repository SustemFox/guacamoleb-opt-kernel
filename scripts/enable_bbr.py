#!/usr/bin/env python3
"""
enable_bbr.py - включить BBR как алгоритм управления заполнением канала.

Version: 1.1 - BBR вместо cubic.

Зачем: в стоковом конфиге CONFIG_TCP_CONG_ADVANCED выключен, поэтому
доступен только cubic, и сменить алгоритм штатно нельзя. На канале с
большой задержкой (мобильная сеть, измеренные 1.2 с) cubic работает плохо:
он заполняет буфер и теряет пакеты. BBR держит скорость при потерях.

Внимание: DEFAULT_TCP_CONG - это не свободная строка, а choice из булевых
опций DEFAULT_*. Поэтому одного CONFIG_TCP_CONG_BBR=y мало: нужен ещё
CONFIG_DEFAULT_BBR=y, а остальные DEFAULT_* надо снять, иначе choice
останется на cubic.

Почему не olddefconfig: включение TCP_CONG_ADVANCED добавляет сразу 17
новых опций TCP_CONG_*, у которых нет значения по умолчанию, и Kconfig
на них прерывается ("aborted"). Поэтому расставляем их сами - тогда
olddefconfig больше не задаёт вопросов.

Usage:
    enable_bbr.py <.config> <net/ipv4/Kconfig> [--bbr] [--cubic]
"""
import re
import sys

VERSION = "1.1"

KEEP_ON = ("TCP_CONG_BBR", "TCP_CONG_CUBIC")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cfg_path, kconfig_path = sys.argv[1], sys.argv[2]
    want_bbr = "--bbr" in sys.argv
    want_cubic = "--cubic" in sys.argv

    kconfig = open(kconfig_path).read()
    options = re.findall(r'^config (TCP_CONG_\w+)', kconfig, re.M)
    if not options:
        sys.exit("не найдено ни одной опции TCP_CONG_* в %s" % kconfig_path)

    lines = open(cfg_path).read().splitlines()
    # убираем прежние упоминания, чтобы не было дублей
    lines = [l for l in lines
             if not re.match(r'^(# )?CONFIG_(TCP_CONG_\w+|DEFAULT_TCP_CONG)=', l)
             and l != 'CONFIG_TCP_CONG_ADVANCED=y'
             and not re.match(r'^# CONFIG_TCP_CONG_ADVANCED is not set$', l)
             and not re.match(r'^(# )?CONFIG_DEFAULT_\w+=', l)]

    defaults = re.findall(r'^\tconfig (DEFAULT_\w+)', kconfig, re.M)
    out = ['CONFIG_TCP_CONG_ADVANCED=y']
    for opt in options:
        if opt in KEEP_ON:
            out.append('CONFIG_%s=y' % opt)
        else:
            out.append('# CONFIG_%s is not set' % opt)
    for opt in defaults:
        if opt == 'DEFAULT_BBR' and want_bbr:
            out.append('CONFIG_%s=y' % opt)
        else:
            out.append('# CONFIG_%s is not set' % opt)
    default = 'bbr' if want_bbr else ('cubic' if want_cubic else 'cubic')
    out.append('CONFIG_DEFAULT_TCP_CONG="%s"' % default)

    with open(cfg_path, 'w') as f:
        f.write('\n'.join(lines + out) + '\n')
    print('enable_bbr %s: опций TCP_CONG_* - %d, default - %s'
          % (VERSION, len(options), default))


if __name__ == '__main__':
    main()
