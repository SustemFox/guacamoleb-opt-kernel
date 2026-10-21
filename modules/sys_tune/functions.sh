#!/system/bin/sh
# Общие функции модуля sys_tune.
# LOG и log/set_read используются и post-fs-data.sh, и service.sh.

LOG=/data/local/tmp/sys-tune.log

log() {
    echo "$(date '+%F %T') sys-tune: $*" >> $LOG
}

# set_read <путь> <желаемое значение> <человекочитаемое имя>
# Записать значение в sysfs/procfs и ПРОВЕРИТЬ результат чтением обратно.
# Раньше модуль только писал и не проверял, из-за чего часть настроек
# молча не применялась.
set_read() {
    _p=$1
    _want=$2
    _name=$3
    if [ ! -e "$_p" ]; then
        log "  $_name: нет $_p - пропуск"
        return 0
    fi
    _cur=$(cat "$_p" 2>/dev/null)
    if [ "$_cur" = "$_want" ]; then
        log "  $_name = $_cur (уже нужное)"
        return 0
    fi
    if echo "$_want" > "$_p" 2>/dev/null; then
        _now=$(cat "$_p" 2>/dev/null)
        if [ "$_now" = "$_want" ]; then
            log "  $_name: $_cur -> $_now (ок)"
        else
            log "  $_name: $_cur -> $_now (НЕ СОВПАЛО, ждали $_want)"
        fi
    else
        log "  $_name: НЕ УДАЛОСЬ записать $_want (было $_cur)"
    fi
}
