# guacamoleb (OnePlus 7) — LineageOS 23.2 kernel, optimization baseline

Builds a flashable **boot.img** for `guacamoleb` from the **LineageOS 23.2**
kernel source with **no root solution**. This repository is the workspace for
**kernel performance / efficiency work** on top of the verified stock build
pipeline.

Derived from `SustemFox/guacamoleb-stock-kernel` (branch `pi/llvm-baseline`),
which was confirmed to build and boot on the device without workarounds.

## Why a separate repo

A fork was not possible (github does not fork a repository into its own
owner account, and no organization is available), so the verified pipeline was
copied here. The upstream `guacamoleb-stock-kernel` stays untouched as the
known-good reference.

## What this builds today

The current `main` is the **unmodified reference build**:

| aspect | how |
|---|---|
| source | `LineageOS/android_kernel_oneplus_sm8150`, pinned commit `0521dc291cf1` |
| configuration | the **exact official `.config`** from the shipped `boot.img` (IKCONFIG, unmodified) |
| toolchain | `clang-r563880c` (build id `14054515`), **pure LLVM** (`LLVM=1 LLVM_IAS=1`) |
| ramdisk + DTB | taken from the official `boot.img`, byte-identical |
| vermagic | pinned to the official release string via `.scmversion` |
| AVB | footer re-signed with `avbtool` and verified |

CI asserts release string and clang build id match the official kernel, and
prints the kernel size delta.

## Optimization work (planned)

Changes belong on a branch, one lever per branch, each measured against `main`:

- **Scheduler / frequency**: EAS/HMP tuning, governor (`schedutil`), latency-nice
- **I/O and mm**: readahead, f2fs/ext4 mount options, writeback, zram, PSI
- **Network**: TCP congestion control (bbr/cubic), buffers
- **Memory**: LMK, `min_free_kbytes`, vmalloc tuning
- **Build**: `-O3` vs `-O2`, dropping unused drivers/subsystems (smaller image,
  faster init), `CONFIG_HZ`
- **Idle / battery**: cpuidle states, suspend tuning

Every change must keep: boot, Wi-Fi (`qca_cld3_wlan` vermagic), vendor modules
(`CONFIG_MODVERSIONS=y`) and Android 16 compatibility.

## Artifacts

* `boot-guacamoleb-opt.img` — flashable boot image
* `Image-opt-<sha>.zip` — raw kernel
* `config-and-log-opt-<sha>.zip` — `.config` + full build log

## Safe test (no flashing)

```bash
fastboot boot boot-guacamoleb-opt.img
```

`fastboot boot` loads the image into RAM without writing the boot partition.

## Install (requires PC)

```bash
# A/B device, active slot
fastboot flash boot boot-guacamoleb-opt.img
```

> This image contains **no root**. Flashing it over a device that relies on
> APatch removes root; keep the APatch-patched boot image for rollback.

## Notes

* **Re-flash after every OTA** (LineageOS OTA writes the inactive slot).
* **SELinux** stays enforcing.
