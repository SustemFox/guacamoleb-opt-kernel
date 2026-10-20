#!/usr/bin/env bash
# fetch_toolchain.sh - найти clang, которым собран официальный kernel.
#
# Зачем искать, а не закреплять URL: официальный kernel banner содержит
# build id тулчейна:
#
#     Linux version 4.14.357-openela-perf-g0521dc291cf1 ...
#     (Android (15071444, +pgo, +bolt, +lto, +mlgo, based on r596125)
#      clang version 22.0.2)
#
# При LTO + ThinLTO + Shadow Call Stack другой clang меняет код ранней
# загрузки - именно так устройство зависает до логотипа. Поэтому build id
# берём из официального boot.img и ищем prebuilt ровно с таким же id.
#
# Порядок поиска:
#   1) закреплённый tarball (CLANG_TARBALL), если задан и совпадает;
#   2) ветка AOSP prebuilts: перебираем каталоги clang-r* от новых к старым,
#      у каждого спрашиваем build id у его bin/clang;
#   3) не нашли - падаем с внятным сообщением (никогда молча).
#
# Использование:
#   fetch_toolchain.sh <official-boot.img> <out-dir> [--list]
set -euo pipefail

BOOT="${1:?official boot.img}"
OUT="${2:?output dir}"
LIST_ONLY=0
[ "${3:-}" = "--list" ] && LIST_ONLY=1

REPO="${PREBUILTS_REPO:-https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86}"
BRANCH="${PREBUILTS_BRANCH:-mirror-goog-llvm-r596125-release}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

WANT=$(python3 "$SCRIPTS/artifact_info.py" --clang-build-id "$BOOT" || true)
if [ -z "$WANT" ]; then
  echo "::error::не удалось прочитать clang build id из $BOOT" >&2
  exit 1
fi
echo "::notice::официальное ядро собрано clang build id = $WANT"

# --- список кандидатов из ветки AOSP ---
list_candidates() {
  curl -s --compressed -m 60 \
    "$REPO/+/refs/heads/$BRANCH/?format=JSON" 2>/dev/null \
    | tail -c +6 \
    | grep -oE '"name": "clang-r[0-9a-z]+"' \
    | sed 's/.*"name": "//; s/"$//' \
    | sort -V -r
}

# --- build id конкретного prebuilt ---
clang_build_id_of() {
  local dir="$1" bin="$2"
  [ -x "$bin/clang" ] || return 1
  "$bin/clang" --version 2>/dev/null \
    | sed -n 's/.*Android (\([0-9]*\),.*/\1/p' | head -1
}

if [ "$LIST_ONLY" = "1" ]; then
  echo "want build id: $WANT"
  echo "candidates:"
  list_candidates | sed 's/^/  /'
  exit 0
fi

mkdir -p "$OUT"

# --- 1) закреплённый tarball ---
if [ -n "${CLANG_TARBALL:-}" ]; then
  echo "::notice::пробую закреплённый CLANG_TARBALL"
  tmp=$(mktemp -d)
  if curl -L --fail --retry 3 --max-time 1200 "$CLANG_TARBALL" -o "$tmp/clang.tar.gz"; then
    tar xzf "$tmp/clang.tar.gz" -C "$tmp"
    found=$(find "$tmp" -maxdepth 3 -name clang -type f -path '*/bin/clang' | head -1 || true)
    if [ -n "$found" ]; then
      got=$(clang_build_id_of "$(dirname "$(dirname "$found")")" "$found" || true)
      if [ "$got" = "$WANT" ]; then
        rm -rf "$OUT/clang"; mkdir -p "$OUT/clang"
        cp -a "$(dirname "$(dirname "$found")")/." "$OUT/clang/"
        echo "::notice::совпало: закреплённый tarball, build id $got"
        exit 0
      fi
      echo "::notice::закреплённый tarball даёт build id '${got:-?}', нужен $WANT"
    fi
  fi
  rm -rf "$tmp"
fi

# --- 2) перебор ветки AOSP ---
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
echo "::notice::ищу prebuilt с build id $WANT в $BRANCH"

for dir in $(list_candidates); do
  echo "::notice::кандидат: $dir"
  url="$REPO/+archive/refs/heads/$BRANCH/$dir.tar.gz"
  if ! curl -L --fail --retry 2 --max-time 1800 -s "$url" -o "$TMP/c.tar.gz"; then
    echo "::notice::  не скачался, пропускаю"
    continue
  fi
  rm -rf "$TMP/x"; mkdir -p "$TMP/x"
  if ! tar xzf "$TMP/c.tar.gz" -C "$TMP/x" 2>/dev/null; then
    echo "::notice::  не распаковался, пропускаю"
    continue
  fi
  found=$(find "$TMP/x" -maxdepth 3 -name clang -type f -path '*/bin/clang' | head -1 || true)
  [ -n "$found" ] || { echo "::notice::  нет bin/clang, пропускаю"; continue; }
  got=$(clang_build_id_of "$(dirname "$(dirname "$found")")" "$found" || true)
  if [ "$got" = "$WANT" ]; then
    rm -rf "$OUT/clang"; mkdir -p "$OUT/clang"
    cp -a "$(dirname "$(dirname "$found")")/." "$OUT/clang/"
    echo "::notice::НАЙДЕНО: $dir, build id $got"
    exit 0
  fi
  echo "::notice::  build id '${got:-?}' != $WANT, пропускаю"
done

echo "::error::prebuilt с clang build id $WANT не найден." >&2
echo "::error::ветка: $BRANCH, репозиторий: $REPO" >&2
echo "::error::доступные каталоги:" >&2
list_candidates | sed 's/^/::error::  /' >&2
echo "::error::официальный образ собран более свежим тулчейном, чем доступный в этой ветке." >&2
exit 1
