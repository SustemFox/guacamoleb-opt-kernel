# guacamoleb (OnePlus 7) — LineageOS 24 reference, 1:1 baseline

Builds a flashable **boot.img** for `guacamoleb` that is **1:1 with the
official LineageOS kernel** of the newest available build. No config delta,
no extra patches, no behavioural change — the only goal of this branch is a
**trustworthy baseline** to measure every later optimization against.

This is the `24` line: the ROM generation that is actually installed on the
device. The older `main` / `opt` / `stocklike` branches stay on the 23.2
toolchain and are left untouched as the historical reference.

## What "1:1" means here, measured

Reference point: official `boot.img` of the LineageOS 24.0 build **20261018**
(`https://download.lineageos.org/api/v2/devices/guacamoleb/builds`).

| | value |
|---|---|
| boot.img | 100 663 296 B, md5 `0608d1fd27c4a3dcbcf25b6c8bb0b696` |
| Image (kernel payload) | **33 422 960 B** |
| Image sha256 | `30317134f93a8119f61808461d50dae5e5d11da7993433f1c445a01ca1532dc7` |
| .config (IKCONFIG) | 161 939 B, 6 061 lines, 1 805 options |
| ramdisk | 59 272 485 B (taken byte-identical from the official image) |
| kernel commit | `0521dc291cf1` (release `4.14.357-openela-perf-g0521dc291cf1`) |
| clang | `Android (15071444, +pgo, +bolt, +lto, +mlgo, based on r596125) clang 22.0.2` / LLD 22.0.2 |
| device config | `/proc/config.gz` on the phone is **byte-identical** to the official IKCONFIG (diff: 0 lines) |

**Acceptance criterion:** the CI gate compares the built kernel against the
official image and fails unless

1. the **clang build id** matches (read from the official image, not hardcoded),
2. the **release string** matches (`-g<sha>` is pinned via `.scmversion`),
3. the **payload sha256** is identical (the appended IKCONFIG is stripped
   before hashing, because `olddefconfig` rewrites it).

`scripts/verify_reference.py` implements that gate and is shared by every
branch, so the comparison baseline is always the official image that CI just
downloaded — never a stale local copy.

## Toolchain: why it is resolved, not pinned

The official kernel states its own toolchain build id in the banner
(`Android (15071444, +pgo, +bolt, +lto, +mlgo, based on r596125)`), so the
expected values are read from the official image instead of being hardcoded.
With LTO + ThinLTO + Shadow Call Stack a different clang changes early-boot
codegen — that is exactly how a device hangs before the logo.

Two things make the lookup non-obvious, both measured:

**1. The right branch is not the one named after the LLVM revision.**
`platform/prebuilts/clang/host/linux-x86` carries several mirrors:

| branch | state |
|---|---|
| `mirror-goog-llvm-r596125-release` | tip Feb 2026, newest prebuilt `clang-r584948b` — **the needed one is absent** |
| `mirror-goog-main-llvm-toolchain-source` | tip Oct 2026, contains `clang-r584948b`, `clang-r596125`, `clang-r614150` — **this is the one** |

**2. The directory is rewritten in place, so the tip holds the wrong build.**
`clang-r596125` was refreshed several times:

```
24 Mar 2026  build 15071444  (commit 9b144bef)   <- the official kernel
Apr 2026     build 15241605
Jun 2026     build 15544236
Jun 2026     build 15682573  (tip)               <- same LLVM rev, other build
```

Same LLVM revision, same clang 22.0.2, different build. So the resolver walks
the branch history for the commit whose message says
`from build <id>`, confirms it with a cheap `BUILD_INFO` read, and only then
downloads the archive from that commit.

The prebuilt binaries are **x86_64 Linux** (ELF machine `0x3e`), so
`bin/clang --version` cannot be executed on the phone. Verification therefore
uses `BUILD_INFO` (`"bid": "15071444"`), not a test run.

`artifact_info.py --llvm-rev` extracts `r596125` from the banner, which is what
names the directory.

## Branches
## Branches

| branch | what it is |
|---|---|
| `24` | **this branch** — 1:1 reference against the official 24.0 kernel |
| `main` | 23.2 reference build (unmodified official config) |
| `opt` | 23.2 + one lever: `CONFIG_SCSI_MQ_DEFAULT=y` (blk-mq UFS path) |
| `stocklike` | 23.2, replicate of a known-green run |

## How the 24 and 23.2 lines relate

* The kernel tree is **the same commit** (`0521dc291cf1`) on both lines —
  `lineage-24.0` was `lineage-23.2` plus one commit
  (`9f007fac`, *power: oplus: Move OEM power supply props to oplus_chg
  class*), and that commit landed **after** the 2026-10-18 build, so the
  newest official image still uses `0521dc291cf1`.
* What **did** change between the lines is the **toolchain**:
  23.2 was built with `clang-r563880c` (build 14054515, clang 21.0.0),
  24.0 with r596125 (build 15071444, clang 22.0.2). That is the single
  reason the `24` branch exists as a separate line.

## Later work (not in this branch)

The device's official `.config` is the baseline. Candidates measured on the
running device:

| lever | official value | note |
|---|---|---|
| `max_cached_processes` | 1024 | userspace (`lmkd`), tunable via `device_config`, no kernel build needed |
| I/O scheduler | `cfq` (legacy) | `CONFIG_SCSI_MQ_DEFAULT` is **not** set; blk-mq with `CONFIG_MQ_IOSCHED_KYBER` is compiled in — that is the `opt` experiment |
| zram size | 2 280 MB | set by `init` from `zramsize=` in the kernel cmdline (DTB `/chosen/bootargs`); `swapoff` returns EINVAL on this kernel, so the size can only be changed at image level |
| scheduler | `CONFIG_SCHED_WALT=y`, `CONFIG_SCHED_TUNE=y` | **WALT, not EAS**; and `sched_tune`, not uclamp |
| `CONFIG_HZ` | 250 | |
| BTF | not built | `CONFIG_DEBUG_INFO` is off; BTF needs `DEBUG_INFO` + `DEBUG_INFO_BTF` and `pahole` ≥ 1.16. The boot partition is filled to the byte by the official image (kernel 33.4 MB + ramdisk 59.3 MB), so debug info does not fit without shrinking the ramdisk — that makes it a separate, non-1:1 branch |
| ftrace | `CONFIG_FUNCTION_TRACER` off | needed for tracing/eBPF work |

## Install

```bash
fastboot flash boot boot-guacamoleb-24-ref.img
```

> This image contains **no root** and **no vendor changes**. Flashing it
> over a device that relies on APatch removes root — keep the APatch-patched
> boot image for rollback.
>
> The stock vendor WLAN module (`qca_cld3_wlan.ko`) is built with
> `CONFIG_MODVERSIONS=y` and only loads against the exact vermagic, which is
> why `pin_vermagic.py` is part of the build.
>
> Re-flash after every OTA (LineageOS OTA writes the inactive slot).
>
> SELinux stays enforcing.
