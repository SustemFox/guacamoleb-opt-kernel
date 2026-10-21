#!/usr/bin/env python3
"""
enable_perf.py - снять накладные расходы ядра, которые на телефоне не нужны.

Version: 1.0

Что и почему:
 * SHADOW_CALL_STACK  - в каждой функции кладётся canary и проверяется при
   выходе. Цена - единицы процентов CPU на каждом вызове. На телефоне
   защита от подделки указателя стека не окупается.
 * DEBUG_LIST         - печатает список указателей при создании каждого
   объекта slab. Это заметный оверхед в системе с тысячами объектов.
 * DEBUG_KERNEL      - включает дополнительные проверки (assert, WARN,
   проверки указателей) по всему ядру.
 * SECURITY_SELINUX_DEVELOP - "разработческий" режим SELinux: печатает все
   отказы AVC (в dmesg их сотни) и ослабляет часть правил.
 * CMA_SIZE_MBYTES   - размер памяти для Contiguous Memory Allocator.
   Стоковое значение 16 МБ мало для буферов камеры и видео: при нехватке
   CMA идёт фрагментация, а запись видео упирается в неё.

Чистим только перечисленные опции - общая маска CONFIG_DEFAULT_* однажды
уже снесла чужие настройки (см. enable_bbr 1.1).

Usage:
    enable_perf.py <.config> [--no-scs] [--no-debug] [--selinux-strict] [--cma N]
"""
import re
import sys

VERSION = "1.0"

OFF = {
    '--no-scs': ['SHADOW_CALL_STACK'],
    '--no-debug': ['DEBUG_LIST', 'DEBUG_KERNEL', 'DEBUG_BUGVERBOSE',
                   'DEBUG_ALIGN_RODATA', 'DEBUG_SPINLOCK',
                   'DEBUG_MUTEXES', 'DEBUG_ATOMIC_SLEEP'],
    '--selinux-strict': ['SECURITY_SELINUX_DEVELOP'],
}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg_path = sys.argv[1]
    args = sys.argv[2:]

    lines = open(cfg_path).read().splitlines()
    out = []
    drop = set()
    cma = None
    for a in args:
        if a in OFF:
            drop.update(OFF[a])
        elif a == '--cma':
            cma = int(args[args.index(a) + 1])
    for line in lines:
        m = re.match(r'^# CONFIG_(\w+) is not set$', line)
        if m and m.group(1) in drop:
            continue
        m2 = re.match(r'^CONFIG_(\w+)=', line)
        if m2 and m2.group(1) in drop:
            continue
        out.append(line)

    for o in sorted(drop):
        out.append('# CONFIG_%s is not set' % o)
    if cma:
        out = [re.sub(r'^CONFIG_CMA_SIZE_MBYTES=.*', 'CONFIG_CMA_SIZE_MBYTES=%d' % cma, l)
               if l.startswith('CONFIG_CMA_SIZE_MBYTES=') else l for l in out]
        if not any(l.startswith('CONFIG_CMA_SIZE_MBYTES=') for l in out):
            out.append('CONFIG_CMA_SIZE_MBYTES=%d' % cma)

    with open(cfg_path, 'w') as f:
        f.write('\n'.join(out) + '\n')
    print('enable_perf %s: отключено %s%s' % (
        VERSION, ', '.join(sorted(drop)),
        (', CMA=%d' % cma) if cma else ''))


if __name__ == '__main__':
    main()
