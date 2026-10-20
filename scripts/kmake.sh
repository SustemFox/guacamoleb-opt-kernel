#!/usr/bin/env bash
# KNOWN-GOOD toolchain wrapper (same invocation as the CI run that produced a booting stock kernel).
set -euo pipefail

: "${CLANG_DIR:?CLANG_DIR not set}"
: "${GCC64_DIR:?GCC64_DIR not set}"
: "${GCC32_DIR:?GCC32_DIR not set}"

exec make "$@" \
  O=out \
  CC="$CLANG_DIR/bin/clang" \
  CLANG_TRIPLE=aarch64-linux-gnu- \
  CROSS_COMPILE="$GCC64_DIR/bin/aarch64-linux-android-" \
  CROSS_COMPILE_ARM32="$GCC32_DIR/bin/arm-linux-androideabi-" \
  LD="$CLANG_DIR/bin/ld.lld" \
  AR="$CLANG_DIR/bin/llvm-ar" \
  NM="$CLANG_DIR/bin/llvm-nm" \
  OBJCOPY="$CLANG_DIR/bin/llvm-objcopy" \
  OBJDUMP="$CLANG_DIR/bin/llvm-objdump" \
  STRIP="$CLANG_DIR/bin/llvm-strip"
