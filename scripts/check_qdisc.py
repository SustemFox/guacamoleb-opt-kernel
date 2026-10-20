#!/usr/bin/env python3
"""
check_qdisc.py - which network schedulers (qdiscs) are really in the kernel?

Same lesson as with the I/O schedulers: the config is not the truth, the
binary is. Every qdisc registers itself with `.id = "<name>"`, and that name
is a NUL-terminated string in .rodata, so the binary can be checked directly.

Usage:
    check_qdisc.py <kernel-image|boot.img> [--require NAME] [--forbid NAME]

Exit code 0 = all requirements satisfied.
"""
import struct
import sys

KNOWN = {
    'pfifo_fast': 'default, 3 bands, no AQM',
    'fq_codel':   'fair queue + CoDel AQM (what Android uses)',
    'fq':         'fair queue with pacing (EDT)',
    'codel':      'CoDel AQM alone',
    'pie':        'PIE AQM',
    'sfq':        'stochastic fair queueing',
    'htb':        'hierarchical token bucket (shaping)',
    'tbf':        'token bucket filter (shaping)',
    'prio':       'priority bands',
    'multiq':     'multiqueue wrapper',
    'red':        'random early detection',
    'netem':      'network emulator',
}


def kernel_region(path):
    blob = open(path, 'rb').read()
    if blob[:8] != b'ANDROID!':
        return blob
    page = struct.unpack('<I', blob[36:40])[0] or 4096
    ksize = struct.unpack('<I', blob[8:12])[0]
    if 0 < ksize <= len(blob) - page:
        return blob[page:page + ksize]
    return blob[page:]


def count_exact(blob, name):
    """Count standalone NUL-terminated occurrences of `name`.

    Exact matching matters: "fq" occurs 150+ times inside other strings,
    but only the standalone form means the sch_fq qdisc is present.
    """
    return blob.count(b'\x00' + name.encode() + b'\x00')


def main():
    argv = sys.argv[1:]
    positional, flags, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a in ('--require', '--forbid'):
            if i + 1 >= len(argv):
                sys.stderr.write('::error::%s needs a name\n' % a)
                return 1
            flags.append((a, argv[i + 1]))
            i += 2
            continue
        positional.append(a)
        i += 1

    if len(positional) != 1:
        print(__doc__)
        return 1

    blob = kernel_region(positional[0])
    found = {n: count_exact(blob, n) for n in KNOWN}

    print('kernel: %s (%d bytes)' % (positional[0].split('/')[-1], len(blob)))
    print('network schedulers in the binary:')
    for name, note in KNOWN.items():
        mark = 'YES' if found[name] else ' no'
        print('  %-12s %s  (%d)  %s' % (name, mark, found[name], note))
    print('')

    ok = True
    for flag, value in flags:
        if flag == '--require':
            if found.get(value, 0):
                print('OK    required scheduler present: %s' % value)
            else:
                print('FAIL  required scheduler MISSING: %s' % value)
                ok = False
        elif flag == '--forbid':
            if found.get(value, 0):
                print('FAIL  forbidden scheduler present: %s' % value)
                ok = False
            else:
                print('OK    forbidden scheduler absent: %s' % value)

    print('')
    print('RESULT: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
