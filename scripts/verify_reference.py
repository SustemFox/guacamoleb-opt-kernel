#!/usr/bin/env python3
"""
verify_reference.py - 1:1 gate between a built kernel and the official one.

Used by every branch of this repository so the tooling stays identical and
the comparison baseline is always the official boot.img that CI just
downloaded. Three checks, in decreasing strictness:

  1. clang build id  - HARD gate. With LTO + ThinLTO + Shadow Call Stack a
     different clang changes early-boot codegen, which is exactly what makes
     a device hang before the logo. The official kernel states its own
     build id in the banner ("Android (15071444, ...) clang version 22.0.2"),
     so the expected value is read from the official image, not hardcoded.
  2. release string  - HARD gate. The stock vendor WLAN module
     (qca_cld3_wlan.ko) is built with CONFIG_MODVERSIONS=y and only loads
     against the exact vermagic of the kernel it was built with.
  3. payload hash   - only with --require-identical. Identical means the
     same bytes; used by the pure reference branch, where no config delta
     and no extra patches are applied.

Usage:
    verify_reference.py <built-kernel|boot.img> <official-boot.img> [--require-identical]
                        [--expect-identical]

Exit code 0 = all requested checks passed.
"""
import hashlib
import re
import struct
import sys

CLANG_ID_RE = re.compile(rb'Android \((\d+),')
RELEASE_RE = re.compile(rb'Linux version (\S+) ')


def read_kernel(path):
    """Return the kernel blob from an Android boot image or a raw Image."""
    blob = open(path, 'rb').read()
    if blob[:8] == b'ANDROID!':
        page = struct.unpack('<I', blob[36:40])[0]
        ksize = struct.unpack('<I', blob[8:12])[0]
        return blob[page:page + ksize]
    return blob


def clang_build_id(kernel):
    m = CLANG_ID_RE.search(kernel)
    return m.group(1).decode() if m else ''


def release_string(kernel):
    for m in RELEASE_RE.finditer(kernel):
        text = m.group(1).decode(errors='replace')
        if '%' not in text:
            return text
    return ''


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def strip_ikconfig(kernel):
    """Split off the IKCONFIG blob appended to the kernel image.

    CONFIG_IKCONFIG=y makes the build append the .config (gzip, prefixed
    with "IKCFG_ST") to the kernel. `olddefconfig` rewrites that .config, so
    its bytes differ from the official one even for a perfect 1:1 build.
    The payload hash must therefore be computed over the kernel *without*
    the appended config; the config size is reported separately.
    """
    i = kernel.rfind(b'IKCFG_ST')
    if i < 0:
        return kernel, 0
    return kernel[:i], len(kernel) - i


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if len(args) != 2:
        print(__doc__)
        return 1

    built = read_kernel(args[0])
    official = read_kernel(args[1])

    built_payload, built_cfg = strip_ikconfig(built)
    official_payload, official_cfg = strip_ikconfig(official)

    built_id = clang_build_id(built)
    official_id = clang_build_id(official)
    built_rel = release_string(built)
    official_rel = release_string(official)
    built_sha = sha256(built_payload)
    official_sha = sha256(official_payload)

    print('official : clang-build-id=%s release=%s payload=%d (+%d cfg) sha256=%s'
          % (official_id or '?', official_rel or '?', len(official_payload),
             official_cfg, official_sha))
    print('built    : clang-build-id=%s release=%s payload=%d (+%d cfg) sha256=%s'
          % (built_id or '?', built_rel or '?', len(built_payload),
             built_cfg, built_sha))
    print('')

    ok = True

    if built_id != official_id:
        print('FAIL  clang build id: built %s != official %s'
              % (built_id or '?', official_id or '?'))
        ok = False
    else:
        print('OK    clang build id matches (%s)' % built_id)

    if built_rel != official_rel:
        print('FAIL  release string: built %r != official %r'
              % (built_rel, official_rel))
        ok = False
    else:
        print('OK    release string matches (%s)' % built_rel)

    if '--require-identical' in flags:
        if built_sha != official_sha:
            print('FAIL  payload sha256 differs (built %s, official %s)'
                  % (built_sha, official_sha))
            ok = False
        else:
            print('OK    payload sha256 identical')
    else:
        delta = len(built) - len(official)
        print('INFO  payload size delta: %+d bytes' % delta)

    if '--expect-identical' in flags and built_sha != official_sha:
        print('NOTE  payload differs - expected for a branch with a config delta')

    print('')
    print('RESULT: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
