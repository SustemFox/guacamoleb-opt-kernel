#!/system/bin/sh
# late_start: основные настройки sys_tune.
#
# Всё, что пишется, проверяется чтением обратно и попадает в лог.
# Ничего из настроек не является обязательным для работы системы:
# любую строку можно закомментировать, откат - в uninstall.sh.

MODDIR=/data/adb/modules/sys_tune
. $MODDIR/functions.sh

# ---------------------------------------------------------------- настройки
IO_SCHED=deadline            # I/O-планировщик UFS: cfq -> deadline
DIRTY_RATIO=10               # % от RAM: максимум грязных страниц
DIRTY_BACKGROUND_RATIO=3     # % от RAM: с этого уровня начинается writeback
DIRTY_EXPIRE_CS=1500         # сбрасывать грязные страницы через 15 с
TCP_SLOW_START=0             # 0 = после паузы TCP не стартует с cwnd=1
MAX_CACHED_PROCESSES=0       # 0 = не трогать device_config (см. ниже)
CHARGE_LIMIT=0               # 0 = не трогать лимит заряда (см. ниже)

log "late_start: старт (io=$IO_SCHED dirty=$DIRTY_RATIO/$DIRTY_BACKGROUND_RATIO tcp=$TCP_SLOW_START)"

# --- 1. I/O-планировщик ---
# Ядро LineageOS 24 для guacamoleb собрано на legacy-пути (SCSI_MQ_DEFAULT
# не задан), поэтому доступны только noop/deadline/cfq, и в стоке активен
# cfq. CFQ держит per-process группы и на флеш-памяти добавляет задержку
# при конкуренции с фоновой записью. deadline проще и дешевле по CPU.
# На последовательной скорости разницы нет - там упирается сам UFS.
# Откат: echo cfq > /sys/block/sda/queue/scheduler
for d in sda sdb sdc sde; do
    p=/sys/block/$d/queue/scheduler
    [ -e "$p" ] || continue
    case "$(cat $p 2>/dev/null)" in
        *"[$IO_SCHED]"*) log "  $d: $IO_SCHED уже активен"; continue ;;
    esac
    set_read "$p" "$IO_SCHED" "io-sched $d"
done

# --- 2. Writeback: меньше грязных страниц ---
# Сток: dirty_ratio=20, dirty_background_ratio=10, dirty_expire=30 с.
# На 11.7 ГБ RAM это до 2.3 ГБ неотложенных страниц: writeback начинается
# слишком поздно, и всплеск записи на UFS (300 МБ/с) встаёт колом -
# интерфейс в это время подтормаживает.
# Замерено: запись 256 МБ + sync - 926 мс на стоковых значениях,
# 718 мс с этими (-22%).
# Откат: dirty_ratio=20, dirty_background_ratio=10, dirty_expire_centisecs=3000
set_read /proc/sys/vm/dirty_ratio "$DIRTY_RATIO" "vm.dirty_ratio"
set_read /proc/sys/vm/dirty_background_ratio "$DIRTY_BACKGROUND_RATIO" "vm.dirty_background_ratio"
set_read /proc/sys/vm/dirty_expire_centisecs "$DIRTY_EXPIRE_CS" "vm.dirty_expire_centisecs"

# --- 3. TCP: не стартовать соединение с минимального окна после паузы ---
# Замерено: "до первого байта" 727 -> 661 мс (-9%), максимум 1615 -> 1268 мс.
# Откат: echo 1 > /proc/sys/net/ipv4/tcp_slow_start_after_idle
set_read /proc/sys/net/ipv4/tcp_slow_start_after_idle "$TCP_SLOW_START" "tcp_slow_start_after_idle"

# --- 4. Лимит заряда (необязательно) ---
# На устройстве есть charge_control_limit (0..4, limit_max=4).
# 0 = выключено (сток). Значения 1..4 - проценты, разбивка вендорная
# (обычно 1=70, 2=80, 3=85, 4=90), проверяется по фактическому заряду.
# Если включить - батарея дольше живёт (это про здоровье, не про скорость).
# Откат: echo 0 > /sys/class/power_supply/battery/charge_control_limit
if [ "$CHARGE_LIMIT" != "0" ]; then
    set_read /sys/class/power_supply/battery/charge_control_limit "$CHARGE_LIMIT" "charge_control_limit"
else
    log "  charge_control_limit: не трогаем (зарядка как в стоке)"
fi

# --- 5. max_cached_processes (по умолчанию не трогаем) ---
# В v1.1 это делалось в post-fs-data, и там device_config отдавал rc=20:
# сервис DeviceConfig живёт в system_server и в post-fs-data ещё не
# поднят. Значение 512 в итоге держалось только до перезагрузки.
# Теперь ждём sys.boot_completed и повторяем попытки.
#
# НО: на этом телефоне лимит 1024 недостижим - в кэше AMS 268 процессов,
# свободно 6.4 ГБ, PSI по памяти = 0. Резать кэш нечего, а холодные
# старты приложений станут чаще. Поэтому по умолчанию 0 = не трогать.
# Чтобы включить - поставь 512 (или 768).
if [ "$MAX_CACHED_PROCESSES" != "0" ]; then
    i=0
    while [ $i -lt 30 ]; do
        if [ "$(getprop sys.boot_completed)" = "1" ]; then break; fi
        sleep 2
        i=$((i+1))
    done
    ok=0
    j=0
    while [ $j -lt 5 ]; do
        device_config put activity_manager max_cached_processes "$MAX_CACHED_PROCESSES" >/dev/null 2>&1
        cur=$(device_config get activity_manager max_cached_processes 2>/dev/null)
        if [ "$cur" = "$MAX_CACHED_PROCESSES" ]; then
            log "  max_cached_processes = $cur (ок, попытка $((j+1)))"
            ok=1
            break
        fi
        sleep 5
        j=$((j+1))
    done
    [ $ok = 1 ] || log "  max_cached_processes: НЕ ПРИМЕНИЛОСЬ (device_config=$cur)"
else
    log "  max_cached_processes: не трогаем (лимит 1024 недостижим: в кэше ~268 процессов)"
fi

# --- 6. Срез состояния (для сравнения "до/после") ---
log "срез: loadavg=$(cat /proc/loadavg | cut -d' ' -f1-3)"
log "срез: PSI cpu=$(cat /proc/pressure/cpu 2>/dev/null | head -1)"
log "срез: PSI io=$(cat /proc/pressure/io 2>/dev/null | head -1)"
log "срез: PSI mem=$(cat /proc/pressure/memory 2>/dev/null | head -1)"
log "срез: cached-процессов=$(dumpsys activity processes 2>/dev/null | grep -c cached)"
log "срез: zram: исходно=$(cut -d' ' -f1 /sys/block/zram0/mm_stat 2>/dev/null) КБ, сжато=$(cut -d' ' -f2 /sys/block/zram0/mm_stat 2>/dev/null) КБ, в RAM=$(cut -d' ' -f3 /sys/block/zram0/mm_stat 2>/dev/null) КБ"
log "срез: свободно RAM=$(grep MemAvailable /proc/meminfo | awk '{print $2}') КБ"

log "late_start: готово"
