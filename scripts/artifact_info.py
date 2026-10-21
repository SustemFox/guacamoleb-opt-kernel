#!/usr/bin/env python3
"""
Version: 1.1 - режим --llvm-rev, выбор build id из истории ветки
Inspect a kernel image or an Android boot image and print metadata.

Used by CI as a gate: the custom kernel must have been produced by the same
clang the official LineageOS kernel was built with, otherwise LTO +
Shadow Call Stack codegen can differ and the device may hang early in boot.

Modes:
    --clang-build-id <image>   build id of the clang that built the kernel,
                               e.g. 15071444 (from "Android (15071444, ...)")
    --llvm-rev        <image>   LLVM revision the toolchain is based on,
                               e.g. r596125 (from "based on r596125")
    --release        <image>   kernel release string
    --info           <image>   all of the above

The kernel payload is located by the appended IKCONFIG blob: the boot header
of this vendor image carries a kernel_size that does not match the real
kernel, so slicing by it would run into the ramdisk.
"""
import re
import struct
import sys
import zlib

BOOT_MAGIC = b'ANDROID!'

CLANG_ID_RE = re.compile(rb'Android \((\d+),')
LLVM_REV_RE = re.compile(rb'based on (r\d+)')
RELEASE_RE = re.compile(rb'Linux version (\S+) ')


def _gzip_end(blob, start):
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


def clang_build_id(kernel):
    m = CLANG_ID_RE.search(kernel)
    return m.group(1).decode() if m else ''


def llvm_rev(kernel):
    m = LLVM_REV_RE.search(kernel)
    return m.group(1).decode() if m else ''


def release_string(kernel):
    for m in RELEASE_RE.finditer(kernel):
        text = m.group(1).decode(errors='replace')
        if '%' not in text:
            return text
    return ''


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    mode, path = sys.argv[1], sys.argv[2]
    k = read_kernel(path)

    if mode == '--clang-build-id':
        print(clang_build_id(k))
    elif mode == '--llvm-rev':
        print(llvm_rev(k))
    elif mode == '--release':
        print(release_string(k))
    elif mode == '--info':
        print('clang_build_id : %s' % clang_build_id(k))
        print('llvm_rev       : %s' % llvm_rev(k))
        print('release        : %s' % release_string(k))
        print('kernel_size    : %d' % len(k))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
