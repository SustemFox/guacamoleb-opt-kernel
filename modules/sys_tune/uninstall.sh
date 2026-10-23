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
set_read /proc/sys/kernel/sched_wakeup_granularity_ns 2000000 "sched_wakeup_granularity_ns"
set_read /proc/sys/kernel/sched_migration_cost_ns 500000 "sched_migration_cost_ns"
set_read /proc/sys/kernel/sched_child_runs_first 0 "sched_child_runs_first"
set_read /proc/sys/kernel/sched_schedstats 1 "sched_schedstats"
set_read /proc/sys/kernel/perf_cpu_time_max_percent 25 "perf_cpu_time_max_percent"
set_read /proc/sys/vm/stat_interval 1 "vm.stat_interval"
for d in sda sdb sdc sde; do
    p=/sys/block/$d/queue
    [ -e "$p/iostats" ] && set_read "$p/iostats" 1 "queue/iostats $d"
    [ -e "$p/nr_requests" ] && set_read "$p/nr_requests" 128 "queue/nr_requests $d"
done
device_config delete activity_manager max_cached_processes >/dev/null 2>&1
