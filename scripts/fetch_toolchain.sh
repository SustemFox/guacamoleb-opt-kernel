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
# Поэтому нужный build ищется по истории: коммит с текстом
# "Update prebuilt Clang to rNNNNNN (...) from build NNNNNNNN".
#
# Так как каталог перезаписывается, архив берётся не с tip, а с того коммита,
# где каталог содержал нужный build.
#
# Использование:
#   fetch_toolchain.sh <official-boot.img> <out-dir> [--list]
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

# --- ищем коммит, где этот каталог содержал нужный build ---
# Коммиты обновления несут в теле "from build NNNNNNNN".
find_commit_for_build() { # <branch>
  curl -s --compressed -m 90 "$REPO/+log/refs/heads/$1?format=JSON&n=400" 2>/dev/null \
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

# --- build id по BUILD_INFO в конкретном коммите (дешёвый запрос, без архива) ---
bid_at_commit() { # <sha> <dir>
  curl -s --compressed -m 40 "$REPO/+/$1/$2/BUILD_INFO?format=TEXT" 2>/dev/null \
    | base64 -d 2>/dev/null \
    | grep -oE '"bid": *"[0-9]+"' | head -1 | grep -oE '[0-9]+'
}

branch_tip() {
  curl -s --compressed -m 60 "$REPO/+log/refs/heads/$1?format=JSON&n=1" 2>/dev/null \
    | tail -c +6 | grep -oE '"commit": "[0-9a-f]{40}"' | head -1 | cut -d'"' -f4
}

if [ "$LIST_ONLY" = "1" ]; then
  echo "want build id : $WANT_ID"
  echo "want llvm rev : $WANT_REV"
  echo "directory     : $DIR"
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    echo "branch $b:"
    echo "  tip          : $(branch_tip "$b")"
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
  if [ -n "$sha" ]; then
    got=$(bid_at_commit "$sha" "$DIR" || true)
    log "ветка $b: коммит ${sha:0:12} даёт $DIR с build id ${got:-?}"
    if [ "$got" = "$WANT_ID" ]; then
      FOUND_SHA="$sha"
      break
    fi
  else
    log "ветка $b: коммита со сборкой $WANT_ID не найдено в истории"
  fi
done

# запасной путь: tip ветки (вдруг каталог не перезаписывали)
if [ -z "$FOUND_SHA" ]; then
  for b in $BRANCHES; do
    [ -n "$b" ] || continue
    sha=$(branch_tip "$b")
    [ -n "$sha" ] || continue
    got=$(bid_at_commit "$sha" "$DIR" || true)
    log "ветка $b: tip ${sha:0:12} даёт build id ${got:-?}"
    [ "$got" = "$WANT_ID" ] && { FOUND_SHA="$sha"; break; }
  done
fi

[ -n "$FOUND_SHA" ] || {
  echo "::error::не найден коммит с $DIR, содержащим clang build id $WANT_ID." >&2
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

# сверяем BUILD_INFO распакованного архива - это не требует запуска бинарника
# (бинарники x86_64 Linux, на телефоне не запускаются)
if [ -f "$TMP/BUILD_INFO" ]; then
  got=$(grep -oE '"bid": *"[0-9]+"' "$TMP/BUILD_INFO" | head -1 | grep -oE '[0-9]+')
  log "BUILD_INFO распакованного тулчейна: build id ${got:-?}"
  [ "$got" = "$WANT_ID" ] || { echo "::error::build id не совпал: ${got:-?} != $WANT_ID" >&2; exit 1; }
fi

rm -rf "$OUT/clang"; mkdir -p "$OUT/clang"
cp -a "$(dirname "$(dirname "$found")")/." "$OUT/clang/"
log "ГОТОВО: $DIR (build $WANT_ID) -> $OUT/clang"
exit 0
