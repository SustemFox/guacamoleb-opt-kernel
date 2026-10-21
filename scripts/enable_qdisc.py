#!/usr/bin/env python3
"""
enable_qdisc.py - сделать fq_codel планировщиком очереди по умолчанию.

Version: 1.0 - fq_codel по умолчанию.

Зачем: в стоке CONFIG_NET_SCH_DEFAULT выключен, поэтому новые сетевые
интерфейсы (и дочерние очереди у mq-интерфейсов, как wlan0) получают
pfifo_fast. Повесить fq_codel на mq-интерфейс из tc нельзя - tc возвращает
ENOENT. Единственный рабочий способ - встроить дефолт в ядро: тогда при
создании интерфейса его очереди сразу получают fq_codel.

Осторожно с чисткой: маска CONFIG_DEFAULT_* слишком широкая, под неё
попадают DEFAULT_SECURITY_SELINUX, DEFAULT_MMAP_MIN_ADDR и другие опции
(в enable_bbr 1.1 это снесло их и ядро перестало загружаться). Поэтому
чистим ТОЛЬКО опции из choice "Default queuing discipline".

Usage:
    enable_qdisc.py <.config> <net/sched/Kconfig> [--fq_codel|--fq|--codel|--pfifo_fast]
"""
import re
import sys

VERSION = "1.0"

CHOICE_OPTS = ('DEFAULT_FQ', 'DEFAULT_CODEL', 'DEFAULT_FQ_CODEL', 'DEFAULT_SFQ',
               'DEFAULT_PFIFO_FAST')
WANT = {'--fq_codel': 'DEFAULT_FQ_CODEL', '--fq': 'DEFAULT_FQ',
        '--codel': 'DEFAULT_CODEL', '--pfifo_fast': 'DEFAULT_PFIFO_FAST'}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cfg_path, kconfig_path = sys.argv[1], sys.argv[2]
    want = 'DEFAULT_FQ_CODEL'
    for arg in sys.argv[3:]:
        if arg in WANT:
            want = WANT[arg]

    kconfig = open(kconfig_path).read()
    # опции именно из choice - иначе снесём чужие CONFIG_DEFAULT_*
    m = re.search(r'^choice\b.*?^endchoice', kconfig, re.M | re.S)
    if not m:
        sys.exit("не найден choice в %s" % kconfig_path)
    opts = re.findall(r'^\tconfig (DEFAULT_\w+)', m.group(), re.M)
    if not opts:
        sys.exit("в choice нет ни одной опции DEFAULT_*")

    lines = open(cfg_path).read().splitlines()
    cleaned = []
    for line in lines:
        mm = re.match(r'^(# )?CONFIG_(\w+)=', line)
        if mm and mm.group(2) in opts:
            continue
        if line in ('CONFIG_NET_SCH_DEFAULT=y', '# CONFIG_NET_SCH_DEFAULT is not set'):
            continue
        cleaned.append(line)

    out = ['CONFIG_NET_SCH_DEFAULT=y']
    for opt in opts:
        if opt == want:
            out.append('CONFIG_%s=y' % opt)
        else:
            out.append('# CONFIG_%s is not set' % opt)
    out.append('CONFIG_DEFAULT_NET_SCH="%s"' % (
        {'DEFAULT_FQ_CODEL': 'fq_codel', 'DEFAULT_FQ': 'fq',
         'DEFAULT_CODEL': 'codel', 'DEFAULT_PFIFO_FAST': 'pfifo_fast'}[want]))

    with open(cfg_path, 'w') as f:
        f.write('\n'.join(cleaned + out) + '\n')
    print('enable_qdisc %s: выбор - %s, опций в choice - %d'
          % (VERSION, want, len(opts)))


if __name__ == '__main__':
    main()
