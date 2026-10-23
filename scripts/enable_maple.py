#!/usr/bin/env python3
"""
enable_maple.py - добавить планировщик Maple I/O в дерево ядра и включить его.

version: 1.0

Зачем: в стоковом конфиге ядро собрано на legacy-пути блочного слоя
(CONFIG_SCSI_MQ_DEFAULT не задан), поэтому доступны только noop/deadline/cfq,
а по умолчанию активен cfq. KYBER и BFQ собираются, но требуют blk-mq и
неприменимы. Maple написан как раз для single-queue API (.ops.sq), поэтому
это единственный "кастомный" планировщик, который здесь реально работает.

Что делает:
 1) кладёт block/maple-iosched.c из kernel-files/;
 2) добавляет IOSCHED_MAPLE и DEFAULT_MAPLE в block/Kconfig.iosched;
 3) добавляет строку сборки в block/Makefile;
 4) ставит CONFIG_IOSCHED_MAPLE=y в .config (планировщик ДОСТУПЕН,
    но по умолчанию остаётся стоковый cfq - чтобы сравнивать на живой
    системе через /sys/block/*/queue/scheduler);
 5) с --o3 меняет -O2 на -O3 для CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE
    (в этом дереве форс -O3 задаётся прямо в Makefile: опция
    CC_OPTIMIZE_FOR_PERFORMANCE_O3 в 4.14 доступна только для ARC).

Usage: enable_maple.py <KERNEL_DIR> [--o3]
"""
import os
import re
import shutil
import sys

VERSION = "1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.pardir, "kernel-files", "maple-iosched.c")

KCONFIG_BLOCK = """
config IOSCHED_MAPLE
\ttristate "Maple I/O scheduler"
\tdefault n
\t---help---
\t  Maple is a simple first-come-first-serve scheduler with separate
\t  read/write queues and read priority. Written for the legacy
\t  (single-queue) block layer, so it applies to this kernel even
\t  without blk-mq.

"""

CHOICE_BLOCK = """
\tconfig DEFAULT_MAPLE
\t\tbool "Maple" if IOSCHED_MAPLE=y
"""

DEFAULT_LINE = '\tdefault "maple" if DEFAULT_MAPLE\n'


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tree = sys.argv[1]
    want_o3 = "--o3" in sys.argv[2:]

    # 1. исходник планировщика
    dst = os.path.join(tree, "block", "maple-iosched.c")
    shutil.copyfile(SRC, dst)
    print("maple %s: block/maple-iosched.c (%d строк)" % (
        VERSION, sum(1 for _ in open(dst))))

    # 2. Kconfig.iosched
    kc = os.path.join(tree, "block", "Kconfig.iosched")
    text = read(kc)
    if "IOSCHED_MAPLE" not in text:
        anchor = "config CFQ_GROUP_IOSCHED"
        if anchor not in text:
            sys.exit("enable_maple: нет якоря %r в block/Kconfig.iosched" % anchor)
        text = text.replace(anchor, KCONFIG_BLOCK.lstrip("\n") + anchor, 1)
        anchor2 = "\tconfig DEFAULT_NOOP"
        if anchor2 not in text:
            sys.exit("enable_maple: нет якоря DEFAULT_NOOP")
        text = text.replace(anchor2, CHOICE_BLOCK.lstrip("\n") + "\n" + anchor2, 1)
        anchor3 = '\tdefault "noop" if DEFAULT_NOOP\n'
        if anchor3 not in text:
            sys.exit("enable_maple: нет строки default noop")
        text = text.replace(anchor3, DEFAULT_LINE + anchor3, 1)
        write(kc, text)
        print("  Kconfig.iosched: IOSCHED_MAPLE + DEFAULT_MAPLE добавлены")
    else:
        print("  Kconfig.iosched: уже есть")

    # 3. block/Makefile
    mk = os.path.join(tree, "block", "Makefile")
    text = read(mk)
    if "maple-iosched.o" not in text:
        anchor = "obj-$(CONFIG_IOSCHED_CFQ)\t+= cfq-iosched.o\n"
        if anchor not in text:
            sys.exit("enable_maple: нет строки cfq-iosched.o в block/Makefile")
        text = text.replace(
            anchor,
            anchor + "obj-$(CONFIG_IOSCHED_MAPLE)\t+= maple-iosched.o\n", 1)
        write(mk, text)
        print("  block/Makefile: строка сборки добавлена")
    else:
        print("  block/Makefile: уже есть")

    # 4. .config
    cfg = os.path.join(tree, "out", ".config")
    if os.path.exists(cfg):
        text = read(cfg)
        if "CONFIG_IOSCHED_MAPLE=y" not in text:
            if "# CONFIG_IOSCHED_MAPLE is not set" in text:
                text = text.replace("# CONFIG_IOSCHED_MAPLE is not set",
                                    "CONFIG_IOSCHED_MAPLE=y", 1)
            else:
                text += "\nCONFIG_IOSCHED_MAPLE=y\n"
            write(cfg, text)
        print("  .config: CONFIG_IOSCHED_MAPLE=y")
    else:
        print("  .config ещё нет - пропуск (запускать после extract_config)")

    # 5. -O3
    if want_o3:
        top = os.path.join(tree, "Makefile")
        text = read(top)
        pat = re.compile(r"(ifdef CONFIG_CC_OPTIMIZE_FOR_SIZE\nKBUILD_CFLAGS   \+= -Os\nelse\nKBUILD_CFLAGS   \+= )-O2\n")
        new, n = pat.subn(r"\g<1>-O3\n", text)
        if n != 1:
            sys.exit("enable_maple: не нашёл ровно один блок -O2 (найдено %d)" % n)
        write(top, new)
        print("  Makefile: KBUILD_CFLAGS -O2 -> -O3")


if __name__ == "__main__":
    main()
