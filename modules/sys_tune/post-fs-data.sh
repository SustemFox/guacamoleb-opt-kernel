#!/system/bin/sh
# post-fs-data: настройки ядра, которые должны быть готовы до старта приложений.
#
# Здесь только то, что не зависит от device_config и не требует system_server.

MODDIR=/data/adb/modules/sys_tune
. $MODDIR/functions.sh

log "post-fs-data: старт"

# --- TCP: не стартовать соединение с минимального окна после паузы ---
# На стоке tcp_slow_start_after_idle = 1: после простоя TCP стартует с
# cwnd=1 и разгоняется заново. На канале с RTT 80-150 мс это добавляет
# сотни мс к открытию каждого соединения.
# Замерено на этом телефоне (30 запросов с паузой 1 с, "до первого байта"):
#   =1 -> 727 мс (максимум 1615 мс)   |   =0 -> 661 мс (максимум 1268 мс)
# Откат: echo 1 > /proc/sys/net/ipv4/tcp_slow_start_after_idle
set_read /proc/sys/net/ipv4/tcp_slow_start_after_idle 0 "tcp_slow_start_after_idle"

# --- page-cluster: не читать "пачками" при подкачке ---
# page-cluster=0 -> ядро читает ровно запрошенные страницы, а не по 8
# подряд. Для zram это правильно: там всё лежит сжатым, и пачечное чтение
# только раздувает I/O. В этом ядре значение уже 0, фиксируем явно.
set_read /proc/sys/vm/page-cluster 0 "vm.page-cluster"

log "post-fs-data: готово"
