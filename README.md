# guacamoleb (OnePlus 7) — LineageOS 24 + kyber (blk-mq)

One lever on top of the 1:1 reference: move the SCSI midlayer to **blk-mq**
and get the **kyber** I/O scheduler instead of legacy CFQ.

Branch `24` is the untouched 1:1 reference. This branch adds exactly one
config delta on top of it, and every step is checked against the official
kernel.

## The delta

| symbol | official | this branch | why |
|---|---|---|---|
| `CONFIG_SCSI_MQ_DEFAULT` | not set | **=y** | on the legacy path only `noop`, `deadline`, `cfq` exist; the mq schedulers are unreachable |
| `CONFIG_MQ_IOSCHED_KYBER` | `=y` in the config, **absent from the binary** | =y, and **verified in the binary** | see below |

Nothing else changes. The release string, the clang build id and the
ramdisk/DTB stay identical to the official image, so the stock vendor WLAN
module still loads.

## Why kyber, not bfq

Measured on the official 24.0 kernel (20261018):

```
noop         YES
deadline     no
mq-deadline  YES
cfq          YES   <- active
kyber        no
bfq          no
```

Both kyber and bfq are **absent from the shipped binary** - so either one
needs the object to actually be linked, not just a config line.

* **kyber** is AOSP's scheduler for modern flash: multi-queue, target
  latencies, self-tuning, minimal overhead. It is `default y` in
  `block/Kconfig.iosched`, so once the build honours the config nothing
  else is needed.
* **bfq** is `default n`, is **not offered as a build-time default** (the
  `choice` block only has DEADLINE / CFQ / NOOP), and trades throughput
  for fairness - on UFS that is usually a bad trade for a phone.

## The trap this branch exists to catch

The official IKCONFIG says:

```
CONFIG_MQ_IOSCHED_KYBER=y
```

but the shipped kernel contains **no kyber code whatsoever** - the
scheduler registration string is absent from the binary. The device still
showed `noop deadline [cfq]`.

A config-only check would have reported "kyber enabled" and shipped a
kernel without kyber. So the build now verifies the **binary**:

```
scripts/check_schedulers.py <image> --require kyber --forbid cfq
```

and fails the CI if kyber did not make it in.

(The same class of bug bit the tooling itself once: the boot header of
this image carries a `kernel_size` that does not match the real kernel,
so slicing by it ran 15.7 MB past the kernel into the ramdisk - and
"kyber" was found there, in the ramdisk, not in the kernel. Hence
`scripts/kernelimg.py`, which locates the kernel by the appended
IKCONFIG instead.)

## After flashing

Kyber and CFQ are both present in the binary, but the **active** scheduler
is still whatever the kernel booted with. To switch at runtime:

```sh
echo kyber > /sys/block/sda/queue/scheduler
```

`block/Kconfig.iosched` has no `DEFAULT_KYBER` in its `choice`, so kyber
cannot be the build-time default - it has to be selected through sysfs
(init.rc or a Magisk module).

## Branches

| branch | what it is |
|---|---|
| `24` | 1:1 reference against the official LineageOS 24.0 kernel |
| `kyber` | **this branch** — `24` + blk-mq + kyber |
| `main` | 23.2 reference build (unmodified official config) |
| `opt` | 23.2 + `CONFIG_SCSI_MQ_DEFAULT=y` (blk-mq UFS path) |
| `stocklike` | 23.2, replicate of a known-green run |

## Install

```bash
fastboot flash boot boot-guacamoleb-24-kyber.img
```

> This image contains **no root** and **no vendor changes**. Flashing it
> over a device that relies on APatch removes root - keep the APatch-patched
> boot image for rollback.
>
> The stock vendor WLAN module (`qca_cld3_wlan.ko`) is built with
> `CONFIG_MODVERSIONS=y` and only loads against the exact vermagic, which is
> why `pin_vermagic.py` is part of the build.
>
> Re-flash after every OTA (LineageOS OTA writes the inactive slot).
>
> SELinux stays enforcing.
