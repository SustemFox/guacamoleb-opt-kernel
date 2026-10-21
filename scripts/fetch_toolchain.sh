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
# Где искать (проверено):
#   * репозиторий: platform/prebuilts/clang/host/linux-x86
#   * актуальная ветка: mirror-goog-main-llvm-toolchain-source
#     (ветки mirror-goog-llvm-rXXXXXX-release - другие, старые зеркала:
#      r596125 там нет, последний коммит - февраль 2026)
#   * каталог называется по ревизии LLVM: clang-r596125
#
# Почему нельзя брать каталог с tip ветки: AOSP обновляет каталог на месте.
# Для r596125 в истории были сборки 15071444 (24 марта) -> 15241605 ->
# 15544236 -> 15682573. Официальное ядро собрано сборкой 15071444, а на tip
# лежит уже 15682573 - та же ревизия LLVM, но другой build.
#
# Как выбирается коммит:
#   1) в истории ветки ищется коммит с текстом
#      "Update prebuilt Clang to rNNNNNN (...) from build NNNNNNNN";
#   2) BUILD_INFO по этому коммиту читается как дешёвая проверка (без
#      скачивания гигабайтного архива). Если он недоступен (rate limit,
#      сеть) - это НЕ повод отбрасывать кандидата: текст коммита уже
#      называет сборку, а окончательная сверка идёт после распаковки;
#   3) архив качается из найденного коммита, и BUILD_INFO распакованного
#      тулчейна сверяется с нужным build id. Несовпадение - ошибка сборки.
#
# Бинарники тулчейна - x86_64 Linux (ELF 0x3e), на телефоне не запускаются,
# поэтому сверка идёт по BUILD_INFO, а не по clang --version.
#
# Использование:
#   fetch_toolchain.sh <official-boot.img> <out-dir> [--list]
# version: 1.1  (BUILD_INFO - необязательная проверка, ветка mirror-goog-main-llvm-toolchain-source)
set -euo pipefail

BOOT="${1:?official boot.img}"
OUT="${2:?output dir}"
LIST_ONLY=0
[ "${3:-}" = "--list" ] && LIST_ONLY=1

REPO="${PREBUILTS_REPO:-https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86}"
BRANCHES="${PREBUILTS_BRANCH:-} mirror-goog-main-llvm-toolchain-source"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

log() { echo "::notice::$*"; }

WANT_ID=$("$SCRIPTS/artifact_info.py" --clang-build-id "$BOOT" || true)
[ -n "$WANT_ID" ] || { echo "::error::не удалось прочитать clang build id из $BOOT" >&2; exit 1; }
WANT_REV=$("$SCRIPTS/artifact_info.py" --llvm-rev "$BOOT" 2>/dev/null || true)
log "официальное ядро: clang build id = $WANT_ID, LLVM = $WANT_REV"

DIR="clang-$WANT_REV"
log "каталог prebuilt: $DIR"

# --- коммит, где этот каталог содержал нужный build ---
find_commit_for_build() { # <branch>
  curl -s --compressed --retry 3 --retry-delay 2 -m 90 \
    "$REPO/+log/refs/heads/$1?format=JSON&n=400" 2>/dev/null \
    | tail -c +6 \
    | python3 -c "
import json,sys
want_build=sys.argv[1]; want_rev=sys.argv[2]
t=sys.stdin.read(); t=t[:t.rfind('}')+1]
try: d=json.loads(t)
except Exception: sys.exit(0)
for c in d.get('log',[]):
    m=c['message']
    if want_build in m and (want_rev in m or 'prebuilt Clang' in m):
        print(c['commit']); break
" "$WANT_ID" "$WANT_REV"
}

# --- build id по BUILD_INFO в конкретном коммите (дешёвая проверка) ---
# Возвращает пусто, если прочитать не удалось: это не приговор кандидату.
bid_at_commit() { # <sha> <dir>
  local body code
  body=$(curl -s --compressed --retry 2 -m 40 -w '\n%{http_code}' \
    "$REPO/+/$1/$2/BUILD_INFO?format=TEXT" 2>/dev/null || true)
  code=$(printf '%s' "$body" | tail -1)
  if [ "$code" != "200" ]; then
    log "  BUILD_INFO: HTTP ${code:-нет ответа} (проверю после распаковки)"
    return 0
  fi
  printf '%s' "$body" | sed '$d' | base64 -d 2>/dev/null \
    | grep -oE '"bid": *"[0-9]+"' | head -1 | grep -oE '[0-9]+' || true
}

branch_tip() {
  curl -s --compressed --retry 3 -m 60 "$REPO/+log/refs/heads/$1?format=JSON&n=1" 2>/dev/null \
    | tail -c +6 | grep -oE '"commit": "[0-9a-f]{40}"' | head -1 | cut -d'"' -f4
}

if [ "$LIST_ONLY" = "1" ]; then
  echo "want build id : $WANT_ID"
  echo "want llvm rev : $WANT_REV"
  echo "directory     : $DIR"
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    echo "branch $b:"
    echo "  tip                : $(branch_tip "$b")"
    echo "  commit для $WANT_ID: $(find_commit_for_build "$b")"
  done
  exit 0
fi

mkdir -p "$OUT"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FOUND_SHA=""
for b in $BRANCHES; do
  [ -n "$b" ] || continue
  sha=$(find_commit_for_build "$b")
  if [ -z "$sha" ]; then
    log "ветка $b: коммита со сборкой $WANT_ID нет в истории"
    continue
  fi
  got=$(bid_at_commit "$sha" "$DIR")
  if [ -z "$got" ]; then
    log "ветка $b: коммит ${sha:0:12} заявляет сборку $WANT_ID, BUILD_INFO недоступен - сверю после распаковки"
    FOUND_SHA="$sha"
    break
  fi
  log "ветка $b: коммит ${sha:0:12} -> $DIR, build id $got"
  if [ "$got" = "$WANT_ID" ]; then
    FOUND_SHA="$sha"
    break
  fi
  log "  build id $got != $WANT_ID, ищу дальше"
done

# запасной путь: tip ветки (вдруг каталог не перезаписывали)
if [ -z "$FOUND_SHA" ]; then
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    sha=$(branch_tip "$b")
    [ -n "$sha" ] || continue
    got=$(bid_at_commit "$sha" "$DIR")
    log "ветка $b: tip ${sha:0:12} даёт build id ${got:-?}"
    [ "$got" = "$WANT_ID" ] && { FOUND_SHA="$sha"; break; }
  done
fi

[ -n "$FOUND_SHA" ] || {
  echo "::error::не найден коммит с $DIR для clang build id $WANT_ID." >&2
  echo "::error::репозиторий: $REPO" >&2
  exit 1
}

log "качаю $DIR @ ${FOUND_SHA:0:12}"
url="$REPO/+archive/$FOUND_SHA/$DIR.tar.gz"
if ! curl -L --fail --retry 3 --retry-delay 5 --max-time 3600 -s "$url" -o "$TMP/c.tar.gz"; then
  echo "::error::не удалось скачать $url" >&2
  exit 1
fi
log "размер архива: $(stat -c%s "$TMP/c.tar.gz" 2>/dev/null) байт"

if ! tar xzf "$TMP/c.tar.gz" -C "$TMP" 2>/dev/null; then
  echo "::error::архив не распаковался" >&2
  exit 1
fi
found=$(find "$TMP" -maxdepth 3 -name clang -type f -path '*/bin/clang' | head -1 || true)
[ -n "$found" ] || { echo "::error::в архиве нет bin/clang" >&2; exit 1; }

# окончательная сверка: BUILD_INFO распакованного тулчейна
if [ -f "$TMP/BUILD_INFO" ]; then
  got=$(grep -oE '"bid": *"[0-9]+"' "$TMP/BUILD_INFO" | head -1 | grep -oE '[0-9]+' || true)
  log "BUILD_INFO распакованного тулчейна: build id ${got:-?}"
  [ "$got" = "$WANT_ID" ] || { echo "::error::build id не совпал: ${got:-?} != $WANT_ID" >&2; exit 1; }
else
  echo "::error::в архиве нет BUILD_INFO - сверить нечем" >&2
  exit 1
fi

rm -rf "$OUT/clang"; mkdir -p "$OUT/clang"
cp -a "$(dirname "$(dirname "$found")")/." "$OUT/clang/"
log "ГОТОВО: $DIR (build $WANT_ID) -> $OUT/clang"
exit 0
