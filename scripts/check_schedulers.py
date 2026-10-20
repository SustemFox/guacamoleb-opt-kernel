#!/usr/bin/env python3
"""
check_schedulers.py - report which I/O schedulers are actually present in a
built kernel image.

Why this exists: the kernel's own .config can claim a scheduler is enabled
while the object was never linked. On the official LineageOS 24.0 build for
guacamoleb the embedded IKCONFIG says

    CONFIG_MQ_IOSCHED_KYBER=y

yet the shipped kernel binary contains no kyber code at all - the scheduler
registration string is simply absent. A config check would have said "kyber
enabled" while the device still showed `noop deadline [cfq]`.

So: do not trust the config, look at the binary. Every I/O scheduler
registers itself with .elevator.name = "<name>", and that name is a plain
NUL-terminated string in .rodata. This tool counts exact NUL-terminated
occurrences of the known scheduler names.

Usage:
    check_schedulers.py <kernel-image|boot.img> [--require NAME] [--forbid NAME]
                         [--json]

Exit code 0 = all requirements satisfied.
"""
import json
import os
import struct
import sys

KNOWN = {
    'noop': 'trivial, no reordering',
    'deadline': 'legacy elevator',
    'mq-deadline': 'blk-mq deadline',
    'cfq': 'legacy CFQ (complete fair queueing)',
    'kyber': 'blk-mq kyber (low overhead, target latencies)',
    'bfq': 'blk-mq BFQ (fair bandwidth, low interactive latency)',
}

# names that are substrings of others and must not be matched standalone
SUBSTRINGS = ('mq-deadline',)


def _gzip_end(blob, start):
    import zlib
    try:
        do = zlib.decompressobj(16 + zlib.MAX_WBITS)
        do.decompress(blob[start:])
        do.flush()
        return start + (len(blob[start:]) - len(do.unused_data))
    except Exception:
        return None


def read_kernel(path):
    """Return the kernel payload from an Android boot image or a raw Image."""
    blob = open(path, 'rb').read()
    if blob[:8] != b'ANDROID!':
        return blob
    page = struct.unpack('<I', blob[36:40])[0] or 4096
    i = blob.find(b'IKCFG_ST', page)
    if i >= 0:
        end = _gzip_end(blob, i + 8)
        if end and end > i:
            return blob[page:end]
    ksize = struct.unpack('<I', blob[8:12])[0]
    if 0 < ksize <= len(blob) - page:
        return blob[page:page + ksize]
    return blob[page:]


def count_exact_string(blob, name):
    """Count NUL-terminated standalone occurrences of `name`."""
    return blob.count(b'\x00' + name.encode() + b'\x00')


def find_schedulers(blob):
    """Return {name: count} for every scheduler name found as a whole string."""
    found = {}
    for name in KNOWN:
        if name in SUBSTRINGS:
            n = blob.count(name.encode() + b'\x00') + blob.count(b'\x00' + name.encode())
        else:
            n = count_exact_string(blob, name)
        if n:
            found[name] = n
    return found


def main():
    argv = sys.argv[1:]
    positional = []
    flags = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--require', '--forbid'):
            if i + 1 >= len(argv):
                sys.stderr.write('::error::%s needs a scheduler name\n' % a)
                return 1
            flags.append((a, argv[i + 1]))
            i += 2
            continue
        if a.startswith('--'):
            flags.append((a, None))
            i += 1
            continue
        positional.append(a)
        i += 1

    if len(positional) != 1:
        print(__doc__)
        return 1

    path = positional[0]
    blob = read_kernel(path)
    found = find_schedulers(blob)

    print('kernel: %s (%d bytes)' % (os.path.basename(path), len(blob)))
    print('I/O schedulers present in the binary:')
    for name in KNOWN:
        mark = 'YES' if name in found else ' no'
        cnt = found.get(name, 0)
        print('  %-12s %s  (%d)  %s' % (name, mark, cnt, KNOWN[name]))
    print('')

    ok = True
    for flag, value in flags:
        if flag == '--require' and value:
            if value in found:
                print('OK    required scheduler present: %s' % value)
            else:
                print('FAIL  required scheduler MISSING: %s' % value)
                ok = False
        elif flag == '--forbid' and value:
            if value in found:
                print('FAIL  forbidden scheduler present: %s' % value)
                ok = False
            else:
                print('OK    forbidden scheduler absent: %s' % value)
        elif flag == '--json':
            print(json.dumps(found, indent=2, sort_keys=True))

    print('')
    print('RESULT: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
