#!/system/bin/sh
# Возврат к стоковым значениям при удалении модуля.
MODDIR=/data/adb/modules/sys_tune
. $MODDIR/functions.sh

log "uninstall: возврат стоковых значений"

set_read /proc/sys/vm/dirty_ratio 20 "vm.dirty_ratio"
set_read /proc/sys/vm/dirty_background_ratio 10 "vm.dirty_background_ratio"
set_read /proc/sys/vm/dirty_expire_centisecs 3000 "vm.dirty_expire_centisecs"
set_read /proc/sys/net/ipv4/tcp_slow_start_after_idle 1 "tcp_slow_start_after_idle"
set_read /sys/class/power_supply/battery/charge_control_limit 0 "charge_control_limit"
for d in sda sdb sdc sde; do
    p=/sys/block/$d/queue/scheduler
    [ -e "$p" ] || continue
    case "$(cat $p 2>/dev/null)" in
        *"[cfq]"*) continue ;;
    esac
    set_read "$p" cfq "io-sched $d"
done
device_config delete activity_manager max_cached_processes >/dev/null 2>&1
