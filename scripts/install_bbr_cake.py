#!/usr/bin/env python3
"""
install_bbr_cake.py - встроить BBR из 4.19 и перенести cake из 4.19 в 4.14.

Version: 1.0

Что делает:
  1. net/ipv4/tcp_bbr.c  <- kernel-files/tcp_bbr_v419.c:
       rs->is_ack_delayed -> убрать (поля нет в 4.14 struct rate_sample)
  2. net/sched/sch_cake.c <- kernel-files/sch_cake_v419.c:
       nla_nest_start_noflag()   -> nla_nest_start()      (5 мест)
       tcf_block_get(a,b,c,d)    -> tcf_block_get(a,b)    (1 место)
       cake_init/cake_change     -> без extack            (2 места)
       cake_tcf_block            -> без extack            (1 место)
  3. Регистрирует cake в net/sched/Kconfig и net/sched/Makefile.
  4. Конфиг: TCP_CONG_ADVANCED=y, TCP_CONG_BBR=y, TCP_CONG_CUBIC=y,
     NET_SCH_CAKE=m, NET_SCH_NETEM=m. Дефолт остаётся cubic,
     модули сами не грузятся.

Usage:
    install_bbr_cake.py <kernel_dir> <config_path>
"""
import os
import re
import shutil
import sys

VERSION = "1.1"
HERE = os.path.dirname(os.path.abspath(__file__))
KERNEL_FILES = os.path.join(os.path.dirname(HERE), "kernel-files")


def die(msg):
    sys.exit("install_bbr_cake %s: %s" % (VERSION, msg))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, t):
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)


def patch_bbr(src):
    n = 0
    if "rs->is_ack_delayed" in src:
        src = src.replace("filter_expired && !rs->is_ack_delayed",
                          "filter_expired")
        if "is_ack_delayed" in src:
            die("is_ack_delayed остался после правки")
        n += 1
    # tcp_tso_autosize в 4.14 объявлена static внутри tcp_output.c.
    # В 4.19-BBR она только упомянута в комментарии - проверяем именно
    # вызов, а не текст, иначе ловим ложное срабатывание.
    for line in src.splitlines():
        code = line.split("/*")[0]
        if "tcp_tso_autosize(" in code:
            die("tcp_tso_autosize вызывается: %s" % line.strip())
    return src, n


def patch_cake(src):
    n = {}
    n["nla_nest_start"] = src.count("nla_nest_start_noflag")
    src = src.replace("nla_nest_start_noflag", "nla_nest_start")

    old = "err = tcf_block_get(&q->block, &q->filter_list, sch, extack);"
    if old not in src:
        die("не найден tcf_block_get в ожидаемом виде")
    src = src.replace(old, "err = tcf_block_get(&q->block, &q->filter_list);")
    n["tcf_block_get"] = 1

    old_init = ("static int cake_init(struct Qdisc *sch, struct nlattr *opt,\n"
                "\t\t     struct netlink_ext_ack *extack)")
    if old_init not in src:
        die("не найдена сигнатура cake_init")
    src = src.replace(old_init,
                      "static int cake_init(struct Qdisc *sch, struct nlattr *opt)")
    # Вложенный вызов внутри cake_init (может быть с переносом строки).
    src = re.sub(r'cake_change\(sch, opt,\s*extack\)', 'cake_change(sch, opt)', src)
    src = src.replace(
        "static int cake_change(struct Qdisc *sch, struct nlattr *opt,\n"
        "\t\t       struct netlink_ext_ack *extack)",
        "static int cake_change(struct Qdisc *sch, struct nlattr *opt)")
    src = src.replace("NL_SET_ERR_MSG_ATTR(extack, tb[TCA_CAKE_NAT],",
                      "NL_SET_ERR_MSG_ATTR(NULL, tb[TCA_CAKE_NAT],")
    n["init_change"] = 1

    old_tb = ("static struct tcf_block *cake_tcf_block(struct Qdisc *sch, unsigned long cl,\n"
              "\t\t\t\t\tstruct netlink_ext_ack *extack)")
    if old_tb not in src:
        die("не найдена сигнатура cake_tcf_block")
    src = src.replace(
        old_tb,
        "static struct tcf_block *cake_tcf_block(struct Qdisc *sch, unsigned long cl)")
    n["cake_tcf_block"] = 1

    # 4b. nf_ct_get_tuple_skb появилась в 4.19. В 4.14 есть
    #     nf_ct_get_tuplepr с явным указанием network header offset.
    if "nf_ct_get_tuple_skb" in src:
        src = src.replace(
            "if (!nf_ct_get_tuple_skb(&tuple, skb))",
            "if (!nf_ct_get_tuplepr(skb, skb_network_offset(skb),\n"
            "\t\t\t\t      NFPROTO_IPV4, dev_net(skb->dev), &tuple))")
        n["nf_ct_get_tuple"] = 1

    # 5. nla_parse_nested_deprecated появился в 4.19; в 4.14 это
    #    nla_parse_nested, у которой extack тоже последний аргумент.
    src = re.sub(r'nla_parse_nested_deprecated\(tb, TCA_CAKE_MAX, opt, cake_policy,\s*extack\)',
                 'nla_parse_nested(tb, TCA_CAKE_MAX, opt, cake_policy, NULL)',
                 src)
    if "nla_parse_nested_deprecated" in src:
        die("nla_parse_nested_deprecated не удалось заменить")
    n["nla_parse_nested"] = 1

    # Остаться может только extack в аргументах nla_parse_nested -
    # в 4.14 она его принимает, это нормально. Всё остальное - ошибка.
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r'\bextack\b', line):
            ctx = src.splitlines()[max(0, i - 3):i]
            if not any("nla_parse_nested" in c for c in ctx):
                die("extack вне nla_parse_nested, строка %d: %s"
                    % (i, line.strip()))
    src = src.replace("NL_SET_ERR_MSG_ATTR(NULL, tb[TCA_CAKE_NAT],",
                      "NL_SET_ERR_MSG_ATTR(NULL, tb[TCA_CAKE_NAT],")
    return src, n


def patch_priv(kdir):
    """Расширить icsk_ca_priv под struct bbr из 4.19.

    struct bbr в 4.19 занимает 96 байт (добавлены extra_acked и
    ack_epoch_*), а ICSK_CA_PRIV_SIZE в 4.14 — 88. Upstream поднял
    размер до 13*8 = 104 байт ровно для этого. Повторяем: +16 байт
    на каждый TCP-сокет.
    """
    path = os.path.join(kdir, "include/net/inet_connection_sock.h")
    text = read(path)
    if "13 * sizeof(u64)" in text:
        print("  priv: уже расширен")
        return
    old = "u64\t\t\t  icsk_ca_priv[88 / sizeof(u64)];\n#define ICSK_CA_PRIV_SIZE      (11 * sizeof(u64))"
    if old not in text:
        die("не нашёл icsk_ca_priv в ожидаемом виде")
    text = text.replace(
        old,
        "u64\t\t\t  icsk_ca_priv[104 / sizeof(u64)];\n"
        "#define ICSK_CA_PRIV_SIZE      (13 * sizeof(u64))")
    write(path, text)
    print("  priv: ICSK_CA_PRIV_SIZE 88 -> 104")


CAKE_UAPI_ANCHOR = "#endif\n"


def patch_uapi_pkt_sched(kdir):
    """Дописать enum-ы CAKE в include/uapi/linux/pkt_sched.h.

    cake из 4.19 разбирает и отдаёт атрибуты TCA_CAKE_* — без этих
    определений он не компилируется. Структуры tc_cake_* ему не нужны,
    только перечисления.
    """
    path = os.path.join(kdir, "include/uapi/linux/pkt_sched.h")
    text = read(path)
    if "TCA_CAKE_UNSPEC" in text:
        print("  uapi: CAKE уже есть")
        return
    block = read(os.path.join(KERNEL_FILES, "cake_uapi.txt"))
    # pkt_sched.h заканчивается на #endif от include guard
    idx = text.rstrip().rfind("#endif")
    if idx < 0:
        die("не нашёл #endif в pkt_sched.h")
    text = text[:idx] + block + "\n" + text[idx:]
    write(path, text)
    print("  uapi: добавлены enum-ы CAKE")


CAKE_KCONFIG = """config NET_SCH_CAKE
\ttristate "Common Applications Kept Enhanced (CAKE)"
\thelp
\t  Say Y here if you want to use the Common Applications Kept Enhanced
\t  (CAKE) queue management algorithm.

\t  To compile this driver as a module, choose M here: the module
\t  will be called sch_cake.

\t  If unsure, say N.

"""


def patch_kbuild(kdir):
    kc = os.path.join(kdir, "net/sched/Kconfig")
    t = read(kc)
    if "config NET_SCH_CAKE" in t:
        print("  Kconfig: cake уже есть")
    else:
        anchor = "config NET_SCH_FQ_CODEL\n"
        if anchor not in t:
            die("не нашёл точку вставки в Kconfig")
        write(kc, t.replace(anchor, CAKE_KCONFIG + anchor, 1))
        print("  Kconfig: добавлен NET_SCH_CAKE")

    mk = os.path.join(kdir, "net/sched/Makefile")
    t = read(mk)
    if "sch_cake.o" in t:
        print("  Makefile: cake уже есть")
    else:
        anchor = "obj-$(CONFIG_NET_SCH_FQ_CODEL)\t+= sch_fq_codel.o\n"
        if anchor not in t:
            die("не нашёл точку вставки в Makefile")
        write(mk, t.replace(anchor, anchor +
                            "obj-$(CONFIG_NET_SCH_CAKE)\t+= sch_cake.o\n", 1))
        print("  Makefile: добавлен sch_cake.o")


def patch_config(cfg_path):
    lines = read(cfg_path).splitlines()

    def setopt(name, value):
        pat = re.compile(r'^(# )?CONFIG_%s(=| is not set)' % re.escape(name))
        out = [l for l in lines if not pat.match(l)]
        out.append("CONFIG_%s=%s" % (name, value) if value != "n"
                   else "# CONFIG_%s is not set" % name)
        return out

    lines = setopt("TCP_CONG_ADVANCED", "y")
    lines = setopt("TCP_CONG_BBR", "y")
    lines = setopt("TCP_CONG_CUBIC", "y")
    lines = setopt("DEFAULT_CUBIC", "y")
    lines = setopt("DEFAULT_BBR", "n")
    lines = setopt("DEFAULT_TCP_CONG", '"cubic"')
    for opt in ("BIC", "CDG", "DCTCP", "WESTWOOD", "HSTCP", "HYBLA",
                "HTCP", "VEGAS", "NV", "VENO", "SCALABLE", "LP",
                "YEAH", "ILLINOIS"):
        lines = setopt("TCP_CONG_" + opt, "n")
    lines = setopt("NET_SCH_CAKE", "m")
    # netem нужен для честного A/B: без искусственных потерь BBR нечего
    # лечить, и разница между алгоритмами тонет в шуме канала.
    lines = setopt("NET_SCH_NETEM", "m")
    write(cfg_path, "\n".join(lines) + "\n")
    return lines


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    kdir, cfg = sys.argv[1], sys.argv[2]
    if not os.path.isdir(os.path.join(kdir, "net/ipv4")):
        die("не похоже на дерево ядра: %s" % kdir)

    print("install_bbr_cake %s" % VERSION)

    src = read(os.path.join(KERNEL_FILES, "tcp_bbr_v419.c"))
    src, nfix = patch_bbr(src)
    dst = os.path.join(kdir, "net/ipv4/tcp_bbr.c")
    if os.path.exists(dst):
        shutil.copy2(dst, dst + ".orig-414")
    write(dst, src)
    print("  tcp_bbr.c: 4.19 -> 4.14, правок %d" % nfix)

    src = read(os.path.join(KERNEL_FILES, "sch_cake_v419.c"))
    src, n = patch_cake(src)
    write(os.path.join(kdir, "net/sched/sch_cake.c"), src)
    print("  sch_cake.c: " + ", ".join("%s=%d" % kv for kv in sorted(n.items())))

    patch_kbuild(kdir)
    patch_uapi_pkt_sched(kdir)
    patch_priv(kdir)

    lines = patch_config(cfg)
    for key in ("TCP_CONG_ADVANCED", "TCP_CONG_BBR", "TCP_CONG_CUBIC",
                "DEFAULT_TCP_CONG", "NET_SCH_CAKE", "NET_SCH_NETEM"):
        for l in lines:
            if re.match(r'^(# )?CONFIG_%s(=| is not set)' % key, l):
                print("  config: %s" % l)
                break


if __name__ == "__main__":
    main()
