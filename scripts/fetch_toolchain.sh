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
# Где искать. Репозиторий prebuilts AOSP зеркалит несколько веток, и
# актуальная - mirror-goog-main-llvm-toolchain-source: в ней лежат
# clang-r584948b, clang-r596125, clang-r614150. Ветки вида
# mirror-goog-llvm-rXXXXXX-release - ДРУГИЕ, более старые зеркала: они
# обновляются реже и нужного prebuilt не содержат (проверено: r596125
# там нет, последний коммит - февраль 2026).
#
# Банкер прямо называет ревизию LLVM ("based on r596125"), а prebuilt
# называется так же (clang-r596125) - значит искать можно точно, без
# перебора. Номер build'а проверяется запуском bin/clang --version.
#
# Использование:
#   fetch_toolchain.sh <official-boot.img> <out-dir> [--list]
set -euo pipefail

BOOT="${1:?official boot.img}"
OUT="${2:?output dir}"
LIST_ONLY=0
[ "${3:-}" = "--list" ] && LIST_ONLY=1

REPO="${PREBUILTS_REPO:-https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86}"
# Актуальная ветка - первой, потом всё, что задано окружением.
BRANCHES="${PREBUILTS_BRANCH:-} mirror-goog-main-llvm-toolchain-source"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

log() { echo "::notice::$*"; }

# --- build id и ревизия LLVM из официального образа ---
WANT_ID=$("$SCRIPTS/artifact_info.py" --clang-build-id "$BOOT" || true)
[ -n "$WANT_ID" ] || { echo "::error::не удалось прочитать clang build id из $BOOT" >&2; exit 1; }
log "официальное ядро собрано clang build id = $WANT_ID"

WANT_REV=$("$SCRIPTS/artifact_info.py" --llvm-rev "$BOOT" 2>/dev/null || true)
log "тулчейн основан на LLVM $WANT_REV"

# --- кандидаты по всем веткам, точное совпадение по ревизии - первым ---
list_candidates() {
  local seen="" out="" b d
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    case " $seen " in *" $b "*) continue ;; esac
    seen="$seen $b"
    out=$(curl -s --compressed -m 60 \
      "$REPO/+/refs/heads/$b/?format=JSON" 2>/dev/null \
      | tail -c +6 \
      | grep -oE '"name": "clang-r[0-9a-z]+"' \
      | sed 's/.*"name": "//; s/"$//' \
      | sort -V -r)
    [ -n "$out" ] || continue
    if [ -n "$WANT_REV" ] && echo "$out" | grep -qx "clang-$WANT_REV"; then
      echo "clang-$WANT_REV"
      echo "$out" | grep -vx "clang-$WANT_REV"
    else
      echo "$out"
    fi
  done | awk '!seen[$0]++'
}

clang_build_id_of() {
  local bin="$1"
  [ -x "$bin" ] || return 1
  "$bin" --version 2>/dev/null | sed -n 's/.*Android (\([0-9]*\),.*/\1/p' | head -1
}

branch_sha() {
  curl -s --compressed -m 60 "$REPO/+log/refs/heads/$1?format=JSON&n=1" 2>/dev/null \
    | tail -c +6 | grep -oE '"commit": "[0-9a-f]{40}"' | head -1 | cut -d'"' -f4
}

if [ "$LIST_ONLY" = "1" ]; then
  echo "want build id: $WANT_ID"
  echo "want llvm rev: $WANT_REV"
  echo "candidates:"
  list_candidates | sed 's/^/  /'
  exit 0
fi

mkdir -p "$OUT"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ищем каталог с точным именем в каждой ветке
for dir in $(list_candidates); do
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    SHA=$(branch_sha "$b")
    [ -n "$SHA" ] || continue
    url="$REPO/+archive/$SHA/$dir.tar.gz"
    log "кандидат: $dir (ветка $b @ ${SHA:0:12})"
    if ! curl -L --fail --retry 2 --max-time 3600 -s "$url" -o "$TMP/c.tar.gz"; then
      log "  не скачался, пропускаю"
      continue
    fi
    rm -rf "$TMP/x"; mkdir -p "$TMP/x"
    if ! tar xzf "$TMP/c.tar.gz" -C "$TMP/x" 2>/dev/null; then
      log "  не распаковался, пропускаю"
      continue
    fi
    found=$(find "$TMP/x" -maxdepth 3 -name clang -type f -path '*/bin/clang' | head -1 || true)
    [ -n "$found" ] || { log "  нет bin/clang, пропускаю"; continue; }
    chmod +x "$found" 2>/dev/null || true
    got=$(clang_build_id_of "$found" || true)
    if [ "$got" = "$WANT_ID" ]; then
      rm -rf "$OUT/clang"; mkdir -p "$OUT/clang"
      cp -a "$(dirname "$(dirname "$found")")/." "$OUT/clang/"
      log "НАЙДЕНО: $dir (ветка $b), build id $got"
      exit 0
    fi
    log "  build id '${got:-?}' != $WANT_ID, пропускаю"
  done
done

echo "::error::prebuilt с clang build id $WANT_ID не найден." >&2
echo "::error::репозиторий: $REPO" >&2
echo "::error::проверенные каталоги:" >&2
list_candidates | sed 's/^/::error::  /' >&2
exit 1
