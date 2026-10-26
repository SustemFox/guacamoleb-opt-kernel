# BBR (из 4.19) + cake: что сделано и что намерено

## Собрано

Ветка `bbr-cake`, коммит `6785287` (первая сборка), CI run `40327647536`.

Образ: `boot-bbr-cake.img`, md5 `4acc7ac6c164a379f05c7a4a6e97733e`.
Прошит APatch'ем пользователем -> `apatch_patched_11282_0.13.9_ljhv.img`,
md5 `ea947855171975c6b3b0e574e2beb978`, в оба слота.

Проверка эквивалентности стоку (verify_reference.py):
- clang build id 15071444 - совпал
- release 4.14.357-openela-perf-g9f007fac27dc - совпал
- image size 49111064 - совпал байт в байт
- payload delta +0
- RESULT: PASS, AVB verify OK

## Что перенесено

BBR из android_kernel_oneplus_sm8250 (4.19), 1119 строк против 970:
добавлен учёт склеенных ACK (extra_acked, ack_epoch_*), пейсинг на 1%
ниже полосы. Правка под 4.14: убрано условие rs->is_ack_delayed -
поля нет в 4.14 struct rate_sample.

cake из 4.19, 3113 строк, в 4.14 отсутствовал. Правки:
- nla_nest_start_noflag -> nla_nest_start (5 мест)
- nla_parse_nested_deprecated -> nla_parse_nested, NULL extack
- tcf_block_get 4 арг -> 2
- cake_init/cake_change/cake_tcf_block без extack
- nf_ct_get_tuple_skb -> nf_ct_get_tuplepr
- enum-ы TCA_CAKE_*/CAKE_* дописаны в uapi/linux/pkt_sched.h
- icsk_ca_priv 88 -> 104 байт (struct bbr вырос до 96)

Ничего не включено по умолчанию: DEFAULT_TCP_CONG=cubic,
cake модулем, не грузится сам.

## Замеры на LTE (Yota), Wi-Fi выключен

Скорость, 10 МБ x3, Мбит/с:

| вариант | прогоны | медиана |
|---|---|---|
| cubic (сток) | 12.08, 11.75, 9.17 | 11.75 |
| bbr | 13.51, 17.81, 14.99 | 14.99 |
| cubic, повтор | 14.23, 8.64, 11.85 | 11.85 |
| bbr, повтор | 23.43, 15.81, 14.85 | 15.81 |

BBR быстрее на 27-33%, воспроизвелось дважды.

RTT до 1.1.1.1: покой / под нагрузкой (avg, max):

| вариант | покой | нагрузка | рост |
|---|---|---|---|
| cubic | 54 | 393 / 743 | x7.3 |
| bbr | 72 | 114 / 249 | x1.6 |
| cubic, повтор | 61 | 641 / 1075 | x10.5 |
| bbr, повтор | 61 | 297 / 700 | x4.9 |

BBR режет задержку под нагрузкой в 2-3.5 раза. Глубина очереди:
cubic pipe 4, bbr pipe 2.

Логи: ~/bench/mnet-{stock,stock2,bbr,bbr2}.txt

## Оговорки

- Мобильная сеть шумит; прогон bbr на 23.43 Мбит/с - выброс.
- Это сравнение cubic vs BBR вообще, не вклад именно ACK-агрегации
  из 4.19: на таком канале его отдельно не измерить.
- Дома эффекта нет (потерь ноль), мерить надо только на мобильной.

## cake на устройстве

modprobe не работает: LineageOS не кладёт modules в boot-образ,
/lib/modules отсутствует. Модуль нужно грузить через insmod.
CI теперь выкладывает kmods-bbr-cake.zip (коммит 6436ee7).
