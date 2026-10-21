#!/usr/bin/env bash
# KNOWN-GOOD toolchain wrapper (same invocation as the CI run that produced a booting stock kernel).
set -euo pipefail

: "${CLANG_DIR:?CLANG_DIR not set}"
: "${GCC64_DIR:?GCC64_DIR not set}"
: "${GCC32_DIR:?GCC32_DIR not set}"

# Вариант "pure LLVM" - ровно как в build.config.aarch64 этого дерева:
#   CROSS_COMPILE=aarch64-linux-gnu-  ->  --target=aarch64-linux-gnu-
#   LLVM=1 LLVM_IAS=1                 ->  ассемблер встроенный в clang
# В варианте с путями к GCC префиксы дают --target=aarch64-linux-android- и
# --prefix=<каталог GCC 4.9>, то есть clang берёт заголовки GCC 4.9 вместо
# своих. Это меняет типы и макросы, а значит весь сгенерированный код.
exec make "$@" \
  O=out \
  LLVM=1 LLVM_IAS=1 \
  CC="$CLANG_DIR/bin/clang" \
  CLANG_TRIPLE=aarch64-linux-gnu- \
  CROSS_COMPILE=aarch64-linux-gnu- \
  CROSS_COMPILE_ARM32=arm-linux-gnueabi- \
  LD="$CLANG_DIR/bin/ld.lld" \
  AR="$CLANG_DIR/bin/llvm-ar" \
  NM="$CLANG_DIR/bin/llvm-nm" \
  OBJCOPY="$CLANG_DIR/bin/llvm-objcopy" \
  OBJDUMP="$CLANG_DIR/bin/llvm-objdump" \
  STRIP="$CLANG_DIR/bin/llvm-strip"
