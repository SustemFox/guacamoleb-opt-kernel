#!/usr/bin/env python3
"""
install_net_updates.py - перенести в 4.14 три правки из более новых ядер.

Version: 1.1

Запускать ПОСЛЕ install_bbr_cake.py.

  net/ipv4/tcp_bbr.c   (по мотивам 6.12)
    1. READ_ONCE/WRITE_ONCE для sk_pacing_rate, sk_max_pacing_rate,
       sk_pacing_shift - 5 мест. Без них компилятор вправе перечитать
       поле между проверкой и записью, а его меняет и другой CPU.
    2. bbr_quantization_budget(): убран параметр gain, условие
       "gain > BBR_UNIT" -> "bbr->cycle_idx == 0". Для
       bbr_pacing_gain[] = {5/4, 3/4, 1, 1, 1, 1, 1, 1} это одно и то же:
       gain > BBR_UNIT только на фазе 0, и она единственная.

  net/ipv4/tcp_cubic.c (по мотивам 6.12)
    3. Hystart в микросекундах:
         hystart_ack_delta (2 мс)   -> hystart_ack_delta_us (2000 мкс)
         bictcp_clock()             -> bictcp_clock_us(sk) из tcp_mstamp
         ca->delay_min              -> мкс вместо "мс << 3"
         HYSTART_DELAY_MIN/MAX      -> 4000/16000 вместо (4U<<3)/(16U<<3)
         msecs_to_jiffies(>>3)      -> usecs_to_jiffies()
         порог ack-train            -> delay_min + hystart_ack_delay(sk),
                                       с делением вдвое при SK_PACING_NONE

Единицы согласованы: sample->rtt_us, delay, curr_rtt, delay_min - всё мкс.
tcp_mstamp обновляется в tcp_rcv_established() на каждом входящем сегменте.

Повторный запуск безопасен: у каждой правки есть маркер, по которому
видно, что она уже применена.

Usage:
    install_net_updates.py <kernel_dir> [--strict]

--strict: считать ошибкой ситуацию, когда файл уже пропатчен. Дерево ядра
в CI клонируется чистым, поэтому "уже на месте" там означает, что правки
пришли ещё откуда-то (например, из patches/*.patch), и порядок применения
перестал быть предсказуемым. Молча продолжать в таком случае нельзя.
"""
import os
import sys

VERSION = "1.1"


def die(msg):
    sys.exit("install_net_updates %s: %s" % (VERSION, msg))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, t):
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)


class Patcher(object):
    def __init__(self, name):
        self.name = name
        self.n = 0

    def sub(self, src, old, new, marker, count=1, label=""):
        """Заменить old на new. marker - фрагмент, который есть только в
        новом варианте; по нему определяется, что правка уже применена."""
        label = label or marker
        if marker in src:
            return src
        if src.count(old) != count:
            die("%s: '%s' встречается %d раз, ожидалось %d"
                % (self.name, label, src.count(old), count))
        self.n += count
        return src.replace(old, new)


def patch_bbr(src):
    p = Patcher("tcp_bbr.c")

    src = p.sub(src,
                "\trate = min_t(u64, rate, sk->sk_max_pacing_rate);",
                "\trate = min_t(u64, rate, READ_ONCE(sk->sk_max_pacing_rate));",
                marker="READ_ONCE(sk->sk_max_pacing_rate)",
                label="bbr_bw_to_pacing_rate: max_pacing_rate")

    src = p.sub(src,
                "\tsk->sk_pacing_rate = bbr_bw_to_pacing_rate(sk, bw, bbr_high_gain);",
                "\tWRITE_ONCE(sk->sk_pacing_rate,\n"
                "\t\t   bbr_bw_to_pacing_rate(sk, bw, bbr_high_gain));",
                marker="WRITE_ONCE(sk->sk_pacing_rate,",
                label="bbr_init_pacing_rate_from_rtt")

    src = p.sub(src,
                "\tif (bbr_full_bw_reached(sk) || rate > sk->sk_pacing_rate)\n"
                "\t\tsk->sk_pacing_rate = rate;",
                "\tif (bbr_full_bw_reached(sk) || rate > READ_ONCE(sk->sk_pacing_rate))\n"
                "\t\tWRITE_ONCE(sk->sk_pacing_rate, rate);",
                marker="rate > READ_ONCE(sk->sk_pacing_rate)",
                label="bbr_set_pacing_rate")

    src = p.sub(src,
                "\treturn sk->sk_pacing_rate < (bbr_min_tso_rate >> 3) ? 1 : 2;",
                "\treturn READ_ONCE(sk->sk_pacing_rate) < (bbr_min_tso_rate >> 3) ? 1 : 2;",
                marker="READ_ONCE(sk->sk_pacing_rate) < (bbr_min_tso_rate",
                label="bbr_min_tso_segs")

    src = p.sub(src,
                "\tbytes = min_t(unsigned long, sk->sk_pacing_rate >> sk->sk_pacing_shift,",
                "\tbytes = min_t(unsigned long,\n"
                "\t\t      READ_ONCE(sk->sk_pacing_rate) >> READ_ONCE(sk->sk_pacing_shift),",
                marker="READ_ONCE(sk->sk_pacing_shift)",
                label="bbr_tso_segs_goal")

    src = p.sub(src,
                "static u32 bbr_quantization_budget(struct sock *sk, u32 cwnd, int gain)",
                "static u32 bbr_quantization_budget(struct sock *sk, u32 cwnd)",
                marker="bbr_quantization_budget(struct sock *sk, u32 cwnd)\n",
                label="bbr_quantization_budget: сигнатура")

    src = p.sub(src,
                "\t/* Ensure gain cycling gets inflight above BDP even for small BDPs. */\n"
                "\tif (bbr->mode == BBR_PROBE_BW && gain > BBR_UNIT)\n"
                "\t\tcwnd += 2;",
                "\t/* Ensure gain cycling gets inflight above BDP even for small BDPs. */\n"
                "\tif (bbr->mode == BBR_PROBE_BW && bbr->cycle_idx == 0)\n"
                "\t\tcwnd += 2;",
                marker="bbr->cycle_idx == 0)",
                label="bbr_quantization_budget: условие")

    src = p.sub(src,
                "\tinflight = bbr_quantization_budget(sk, inflight, gain);",
                "\tinflight = bbr_quantization_budget(sk, inflight);",
                marker="bbr_quantization_budget(sk, inflight);",
                label="bbr_inflight: вызов")

    src = p.sub(src,
                "\ttarget_cwnd = bbr_quantization_budget(sk, target_cwnd, gain);",
                "\ttarget_cwnd = bbr_quantization_budget(sk, target_cwnd);",
                marker="bbr_quantization_budget(sk, target_cwnd);",
                label="bbr_set_cwnd: вызов")

    return src, p


def patch_cubic(src):
    p = Patcher("tcp_cubic.c")

    src = p.sub(src,
                "static int hystart_ack_delta __read_mostly = 2;",
                "static int hystart_ack_delta_us __read_mostly = 2000;",
                marker="hystart_ack_delta_us __read_mostly",
                label="hystart_ack_delta_us")

    src = p.sub(src,
                "module_param(hystart_ack_delta, int, 0644);\n"
                "MODULE_PARM_DESC(hystart_ack_delta, \"spacing between ack's indicating train (msecs)\");",
                "module_param(hystart_ack_delta_us, int, 0644);\n"
                "MODULE_PARM_DESC(hystart_ack_delta_us, \"spacing between ack's indicating train (usecs)\");",
                marker="module_param(hystart_ack_delta_us",
                label="module_param")

    src = p.sub(src,
                "#define HYSTART_DELAY_MIN\t(4U<<3)\n"
                "#define HYSTART_DELAY_MAX\t(16U<<3)",
                "#define HYSTART_DELAY_MIN\t(4000U)\t/* 4 ms */\n"
                "#define HYSTART_DELAY_MAX\t(16000U)\t/* 16 ms */",
                marker="#define HYSTART_DELAY_MIN\t(4000U)",
                label="HYSTART_DELAY_MIN/MAX")

    src = p.sub(src,
                "\tu32\tdelay_min;\t/* min delay (msec << 3) */",
                "\tu32\tdelay_min;\t/* min delay (usec) */",
                marker="/* min delay (usec) */",
                label="delay_min: единицы")

    src = p.sub(src,
                "static inline u32 bictcp_clock(void)\n"
                "{\n"
                "#if HZ < 1000\n"
                "\treturn ktime_to_ms(ktime_get_real());\n"
                "#else\n"
                "\treturn jiffies_to_msecs(jiffies);\n"
                "#endif\n"
                "}",
                "/* tcp_mstamp обновляется в tcp_rcv_established() на каждом входящем\n"
                " * сегменте, поэтому это честные микросекунды без обращения к\n"
                " * ktime_get_real() на каждый ACK.\n"
                " */\n"
                "static inline u32 bictcp_clock_us(const struct sock *sk)\n"
                "{\n"
                "\treturn tcp_sk(sk)->tcp_mstamp;\n"
                "}",
                marker="bictcp_clock_us(const struct sock *sk)",
                label="bictcp_clock -> bictcp_clock_us")

    src = p.sub(src,
                "\tca->round_start = ca->last_ack = bictcp_clock();",
                "\tca->round_start = ca->last_ack = bictcp_clock_us(sk);",
                marker="ca->last_ack = bictcp_clock_us(sk);",
                label="bictcp_hystart_reset")

    src = p.sub(src,
                "\tt += msecs_to_jiffies(ca->delay_min >> 3);",
                "\tt += usecs_to_jiffies(ca->delay_min);",
                marker="usecs_to_jiffies(ca->delay_min)",
                label="bictcp_update")

    src = p.sub(src,
                "static void hystart_update(struct sock *sk, u32 delay)\n",
                "/* Насколько пейсинг может растянуть доставку ACK. При малом RTT\n"
                " * хотим хотя бы один TSO-пакет в сети и один в qdisc; множитель 4 -\n"
                " * потому что rate здесь уже удвоен. Потолок - 1 мс.\n"
                " */\n"
                "static u32 hystart_ack_delay(const struct sock *sk)\n"
                "{\n"
                "\tunsigned long rate;\n"
                "\n"
                "\trate = READ_ONCE(sk->sk_pacing_rate);\n"
                "\tif (!rate)\n"
                "\t\treturn 0;\n"
                "\treturn min_t(u64, USEC_PER_MSEC,\n"
                "\t\t     div64_ul((u64)sk->sk_gso_max_size * 4 * USEC_PER_SEC, rate));\n"
                "}\n"
                "\n"
                "static void hystart_update(struct sock *sk, u32 delay)\n",
                marker="static u32 hystart_ack_delay(const struct sock *sk)",
                label="hystart_ack_delay()")

    src = p.sub(src,
                "\tstruct bictcp *ca = inet_csk_ca(sk);\n"
                "\n"
                "\tif (ca->found & hystart_detect)",
                "\tstruct bictcp *ca = inet_csk_ca(sk);\n"
                "\tu32 threshold;\n"
                "\n"
                "\tif (ca->found & hystart_detect)",
                marker="\tu32 threshold;\n\n\tif (ca->found & hystart_detect)",
                label="hystart_update: threshold")

    src = p.sub(src,
                "\t\tu32 now = bictcp_clock();\n"
                "\n"
                "\t\t/* first detection parameter - ack-train detection */\n"
                "\t\tif ((s32)(now - ca->last_ack) <= hystart_ack_delta) {\n"
                "\t\t\tca->last_ack = now;\n"
                "\t\t\tif ((s32)(now - ca->round_start) > ca->delay_min >> 4) {",
                "\t\tu32 now = bictcp_clock_us(sk);\n"
                "\n"
                "\t\t/* first detection parameter - ack-train detection */\n"
                "\t\tif ((s32)(now - ca->last_ack) <= hystart_ack_delta_us) {\n"
                "\t\t\tca->last_ack = now;\n"
                "\n"
                "\t\t\tthreshold = ca->delay_min + hystart_ack_delay(sk);\n"
                "\n"
                "\t\t\t/* Hystart ack train triggers if we get ack past\n"
                "\t\t\t * ca->delay_min/2.\n"
                "\t\t\t * Pacing might have delayed packets up to RTT/2\n"
                "\t\t\t * during slow start.\n"
                "\t\t\t */\n"
                "\t\t\tif (sk->sk_pacing_status == SK_PACING_NONE)\n"
                "\t\t\t\tthreshold >>= 1;\n"
                "\n"
                "\t\t\tif ((s32)(now - ca->round_start) > threshold) {",
                marker="threshold = ca->delay_min + hystart_ack_delay(sk);",
                label="ack-train: порог")

    src = p.sub(src,
                "\tdelay = (sample->rtt_us << 3) / USEC_PER_MSEC;",
                "\tdelay = sample->rtt_us;",
                marker="\tdelay = sample->rtt_us;",
                label="bictcp_acked: delay")

    return src, p


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv[1:]
    if len(args) < 1:
        sys.exit(__doc__)
    kdir = args[0]
    if not os.path.isdir(os.path.join(kdir, "net/ipv4")):
        die("не похоже на дерево ядра: %s" % kdir)

    print("install_net_updates %s%s"
          % (VERSION, " (strict)" if strict else ""))

    total = 0
    already = []
    for fname, fn in (("tcp_bbr.c", patch_bbr), ("tcp_cubic.c", patch_cubic)):
        path = os.path.join(kdir, "net/ipv4", fname)
        src, p = fn(read(path))
        if p.n:
            write(path, src)
            print("  %s: применено %d правок" % (fname, p.n))
        else:
            print("  %s: уже на месте" % fname)
            already.append(fname)
        total += p.n

    if strict and already:
        die("в strict-режиме файлы уже были пропатчены: %s. "
            "На чистом дереве это значит, что правки пришли из другого "
            "источника - проверьте patches/*.patch." % ", ".join(already))

    print("готово, всего новых правок: %d" % total)


if __name__ == "__main__":
    main()
