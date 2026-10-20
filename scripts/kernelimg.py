#!/usr/bin/env python3
"""
kernelimg.py - locate the kernel payload inside an Android boot image.

Shared by check_schedulers.py and verify_reference.py.

Why this needs care: the boot header of this particular vendor image does
not carry a usable kernel_size (the field at offset 8 reads 49 111 064
while the kernel is 33 459 221 bytes long), so slicing by that field
silently runs 15.7 MB past the end of the kernel and into the ramdisk.
Strings from the ramdisk then look like kernel symbols - that is how
"kyber" appeared in a kernel that does not contain kyber at all.

The reliable end marker is the IKCONFIG blob: with CONFIG_IKCONFIG=y the
build appends the .config to the kernel, prefixed by "IKCFG_ST", and the
kernel image ends right after that gzip stream.
"""
import struct
import sys
import zlib

BOOT_MAGIC = b'ANDROID!'


def _gzip_end(blob, start):
    """Return the offset just past the gzip stream starting at `start`."""
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
    if blob[:8] != BOOT_MAGIC:
        return blob

    page = struct.unpack('<I', blob[36:40])[0]
    if not page:
        page = 4096

    # IKCONFIG is appended to the kernel: the kernel ends after that gzip.
    i = blob.find(b'IKCFG_ST', page)
    if i >= 0:
        end = _gzip_end(blob, i + 8)
        if end and end > i:
            return blob[page:end]

    # Fallback: trust the header only if it looks sane.
    ksize = struct.unpack('<I', blob[8:12])[0]
    if 0 < ksize <= len(blob) - page:
        return blob[page:page + ksize]
    return blob[page:]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    k = read_kernel(sys.argv[1])
    print('kernel payload: %d bytes' % len(k))
    print('starts with arm64 Image magic: %s'
          % ('yes' if k[56:60] == b'ARMd' else 'no'))
    i = k.find(b'Linux version')
    print('version banner at offset: %s' % (i if i >= 0 else 'not found'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
