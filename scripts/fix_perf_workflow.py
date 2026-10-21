#!/usr/bin/env python3
"""
fix_perf_workflow.py - починить CI для perf-веток.

version: 1.0

Что было сломано:
 1. В .github/workflows/build.yml у perf-веток остался триггер
    `branches: [24]`, поэтому пуш в perf-scs/perf-full вообще не
    запускал сборку (в списке запусков их не было).
 2. Переменная PERF_FLAGS была объявлена, но scripts/enable_perf.py
    нигде не вызывался - дельта конфига не применялась ни к чему.
 3. Шаг "Verify equivalence" требует совпадения со стоковым ядром,
    а для perf-варианта это по определению неверно.
 4. Имена артефактов были одинаковыми у всех веток.

Usage: fix_perf_workflow.py <file.yml> <branch-name>
"""
import sys

OLD_NAME = "name: guacamoleb 24 reference (stock-equivalent)"
NEW_NAME = "name: guacamoleb kernel (${{ github.ref_name }})"

REPL = [
    # 1. триггер: ветка должна слушать саму себя
    ("    branches: [24]\n", "    branches: [__BRANCH__]\n"),
    # 2. имя прогона
    (OLD_NAME + "\n", NEW_NAME + "\n"),
    # 3. применение дельты конфига до olddefconfig
    ("          # Эталонная линия: конфиг официальный, без единой правки.\n",
     "          # Дельта производительности поверх официального конфига:\n"
     "          # SCS, отладочные опции, SELinux develop, размер CMA.\n"
     "          python3 \"$GITHUB_WORKSPACE/scripts/enable_perf.py\" out/.config $PERF_FLAGS\n"),
    # 4. аудит: печатаем, что реально осталось в конфиге после olddefconfig
    ("          echo \"KERNEL_RELEASE=$(bash ./kmake.sh -s kernelrelease 2>/dev/null | tail -1)\" >> \"$GITHUB_ENV\"\n",
     "          echo \"::notice::effective perf options:\"\n"
     "          grep -E '^(# )?CONFIG_(SHADOW_CALL_STACK|DEBUG_LIST|DEBUG_KERNEL|DEBUG_BUGVERBOSE|DEBUG_ALIGN_RODATA|SECURITY_SELINUX_DEVELOP|CMA_SIZE_MBYTES)' out/.config || true\n"
     "          echo \"KERNEL_RELEASE=$(bash ./kmake.sh -s kernelrelease 2>/dev/null | tail -1)\" >> \"$GITHUB_ENV\"\n"),
    # 5. проверка эквивалентности стоку - только для эталонной линии
    ("      - name: Verify equivalence with the official kernel\n        run: |",
     "      - name: Verify equivalence with the official kernel\n"
     "        # У perf-варианта совпадение со стоком невозможно по определению.\n"
     "        if: ${{ env.PERF_FLAGS == '' }}\n"
     "        run: |"),
    # 6. уникальные имена артефактов
    ("name: boot-guacamoleb-24-ref\n", "name: boot-${{ github.ref_name }}\n"),
    ("boot-guacamoleb-24-ref.img", "boot-${{ github.ref_name }}.img"),
    ("name: Image-24-ref-${{ github.sha }}", "name: Image-${{ github.ref_name }}-${{ github.sha }}"),
]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, branch = sys.argv[1], sys.argv[2]
    text = open(path, encoding='utf-8').read()
    for old, new in REPL:
        new = new.replace("__BRANCH__", branch)
        if old not in text:
            sys.exit("НЕ НАЙДЕНО: %r" % old[:70])
        text = text.replace(old, new)
    open(path, 'w', encoding='utf-8').write(text)
    print("fix_perf_workflow: %s готов (%s)" % (path, branch))


if __name__ == '__main__':
    main()
