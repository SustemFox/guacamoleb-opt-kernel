#!/usr/bin/env python3
"""
Version: 1.0 - сравнение размеров образа
Print kernel sizes and the delta between an official boot image and a custom
kernel image.

Usage:
    compare_size.py <official-boot.img> <new-image-or-boot.img>
"""
import struct
import sys


def kernel_size(path):
    d = open(path, 'rb').read()
    if d[:8] == b'ANDROID!':
        return struct.unpack('<I', d[8:12])[0]
    return len(d)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    o, n = kernel_size(sys.argv[1]), kernel_size(sys.argv[2])
    print('official kernel: %d' % o)
    print('our kernel     : %d' % n)
    print('delta          : %+d bytes (%.3f%%)' % (n - o, 100.0 * (n - o) / o))
    return 0


if __name__ == '__main__':
    sys.exit(main())
