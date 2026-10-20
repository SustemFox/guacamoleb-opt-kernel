#!/usr/bin/env python3
"""
diff_report.py - where exactly does a built Image differ from the official one?

The 1:1 gate can only say "hashes differ". This tool says *where* and *how*:
it slices the official kernel region out of boot.img by the boot header's
kernel_size (the IKCONFIG blob sits in the middle of the image, so cutting at
IKCFG_ST truncates ~15 MB of real kernel), then walks both images byte by
byte, groups the differences into ranges and dumps the first bytes of each.

Usage:
    diff_report.py <built-image> <official-boot.img|official-image> [--top N]
"""
import struct
import sys

MAGIC = b'ANDROID!'
CFG_START = b'IKCFG_ST'
CFG_END = b'IKCFG_ED'


def kernel_region(path):
    blob = open(path, 'rb').read()
    if blob[:8] != MAGIC:
        return blob, 'raw image'
    page = struct.unpack('<I', blob[36:40])[0] or 4096
    ksize = struct.unpack('<I', blob[8:12])[0]
    if 0 < ksize <= len(blob) - page:
        return blob[page:page + ksize], 'boot.img kernel_size=%d' % ksize
    return blob[page:], 'boot.img (kernel_size unusable)'


def cfg_span(img):
    i = img.find(CFG_START)
    if i < 0:
        return None
    j = img.find(CFG_END, i)
    if j < 0:
        return None
    return i, j + len(CFG_END)


def printable(b):
    out = []
    for ch in b:
        out.append(chr(ch) if 32 <= ch < 127 else '.')
    return ''.join(out)


def banner(img):
    i = img.find(b'Linux version ')
    if i < 0:
        return '(not found)'
    j = img.find(b'\x00', i)
    return img[i:j].decode('utf-8', 'replace')


def main():
    argv = sys.argv[1:]
    top = 25
    if '--top' in argv:
        k = argv.index('--top')
        top = int(argv[k + 1])
        del argv[k:k + 2]
    if len(argv) != 2:
        print(__doc__)
        return 1

    built, bhow = kernel_region(argv[0])
    official, ohow = kernel_region(argv[1])

    print('built    : %s  %d bytes  (%s)' % (argv[0], len(built), bhow))
    print('official : %s  %d bytes  (%s)' % (argv[1], len(official), ohow))
    print('size delta: %+d' % (len(built) - len(official)))
    print('')

    for name, img in (('built', built), ('official', official)):
        span = cfg_span(img)
        if span:
            print('%-8s IKCONFIG at %d..%d (%d bytes)' % (name, span[0], span[1], span[1] - span[0]))
        else:
            print('%-8s no IKCONFIG blob' % name)
    print('')

    print('built    banner: %s' % banner(built)[:160])
    print('official banner: %s' % banner(official)[:160])
    print('')

    n = min(len(built), len(official))
    diffs = [i for i in range(n) if built[i] != official[i]]
    print('compared %d bytes, %d differ (%.4f%%)' % (n, len(diffs), 100.0 * len(diffs) / n if n else 0))
    if len(built) != len(official):
        print('NOTE: tails beyond %d bytes were not compared' % n)
    if not diffs:
        print('RESULT: identical over the common length')
        return 0
    print('')

    ranges = []
    start = prev = diffs[0]
    for i in diffs[1:]:
        if i - prev > 32:
            ranges.append((start, prev))
            start = i
        prev = i
    ranges.append((start, prev))
    print('%d difference range(s) (gaps > 32 bytes split a range)' % len(ranges))
    print('')

    bspan = cfg_span(built)
    for start, end in ranges[:top]:
        ln = end - start + 1
        where = ''
        if bspan and bspan[0] <= start < bspan[1]:
            where = '  [inside IKCONFIG]'
        print('@0x%08x (%d) len=%d%s' % (start, start, ln, where))
        print('  built    %s' % built[start:start + 48].hex())
        print('  official %s' % official[start:start + 48].hex())
        print('  built    |%s|' % printable(built[start:start + 48]))
        print('  official |%s|' % printable(official[start:start + 48]))
    if len(ranges) > top:
        rest = sum(e - s + 1 for s, e in ranges[top:])
        print('... %d more range(s), %d bytes total' % (len(ranges) - top, rest))

    total = sum(e - s + 1 for s, e in ranges)
    print('')
    print('TOTAL differing bytes: %d in %d range(s)' % (total, len(ranges)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
