# Отложено: что перенести, когда найдётся ещё что-то

## Из BBR 5.4 (sm8350) — две правки, обе микрооптимизации

1. `bbr_quantization_budget`: условие `gain > BBR_UNIT` -> `bbr->cycle_idx == 0`.
   В PROBE_BW фаза цикла точнее, чем сравнение gain.
   Файл: net/ipv4/tcp_bbr.c, функция bbr_quantization_budget.

2. `READ_ONCE(sk->sk_pacing_shift)` в bbr_tso_segs_goal и
   bbr_rate_bytes_per_sec. Защита от гонки при смене pacing_shift.
   В 4.14 безвредно и без неё.

## НЕ переносится (проверено)

- `bbr_packets_in_net_at_edt()` из 5.4 — нужны tp->tcp_clock_cache
  и tp->tcp_wstamp_ns, которых в 4.14 tcp.h нет вообще (0 совпадений).
  Это EDT-пейсинг, работает только вместе с tcp_output.c из 5.x.
- BBRv2 — нет ни в 4.19, ни в 5.4 (bbr2=0 во всех деревьях LineageOS).

## Проверено и закрыто

- Все 14 веток android_kernel_oneplus_sm8150: BBR 967-970 строк,
  extra_acked=0 во всех. Чистого 4.14-кода новее 2017 года нет.
- google_msm-4.14, nubia_sm8150: то же самое.
- 4.19-деревья (oneplus/xiaomi/motorola/samsung sm8250): 1119 строк,
  extra_acked=33 — это и есть то, что мы уже перенесли.
