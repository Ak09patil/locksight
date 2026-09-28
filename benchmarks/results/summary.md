# LockSight benchmark results

Mode: full. Generated 2026-09-28 12:11, took 150 s.


## 1. Detection time vs graph size

| graph | processes | tarjan_ms | matrix_ms | tarjan_deadlocked | matrix_deadlocked |
|---|---|---|---|---|---|
| random | 10 | 0.009 | 0.025 | 0 | 0 |
| random | 50 | 0.045 | 0.08 | 0 | 0 |
| random | 100 | 0.095 | 0.162 | 0 | 0 |
| random | 250 | 0.249 | 0.405 | 0 | 0 |
| random | 500 | 0.513 | 0.886 | 0 | 0 |
| random | 1000 | 1.18 | 1.683 | 0 | 0 |
| random | 2000 | 2.497 | 3.57 | 0 | 0 |
| random | 5000 | 6.556 | 10.489 | 0 | 0 |
| random | 10000 | 13.156 | 21.702 | 4 | 11 |
| worst-case chain | 10 | 0.011 | 0.026 | 0 | 0 |
| worst-case chain | 50 | 0.056 | 0.27 | 0 | 0 |
| worst-case chain | 100 | 0.115 | 0.978 | 0 | 0 |
| worst-case chain | 250 | 0.295 | 6.251 | 0 | 0 |
| worst-case chain | 500 | 0.603 | 24.503 | 0 | 0 |
| worst-case chain | 1000 | 1.343 | 94.03 | 0 | 0 |
| worst-case chain | 2000 | 2.784 | 409.892 | 0 | 0 |
| worst-case chain | 5000 | 7.057 | 2776.75 | 0 | 0 |
| worst-case chain | 10000 | 16.276 | 11271.582 | 0 | 0 |

## 2. On-block vs periodic detection

| scenario | mode | throughput_per_s | wall_time_s | aborts | detection_runs | detection_time_ms |
|---|---|---|---|---|---|---|
| bank | on-block | 131.3 | 0.459 | 21 | 129.3 | 17.64 |
| bank | periodic 10 ms | 61.6 | 0.986 | 45 | 78.7 | 23.02 |
| bank | periodic 50 ms | 20.5 | 3.274 | 60.3 | 60 | 27.95 |
| bank | periodic 200 ms | 5.8 | 10.865 | 54 | 52.7 | 26.14 |
| philosophers | on-block | 52.8 | 0.461 | 10.7 | 52.7 | 5.55 |
| philosophers | periodic 10 ms | 44.0 | 0.557 | 13.7 | 45.7 | 5.28 |
| philosophers | periodic 50 ms | 25.5 | 1.027 | 14.3 | 18.3 | 4.3 |
| philosophers | periodic 200 ms | 7.9 | 3.671 | 17 | 17.3 | 5.08 |
| stress | on-block | 164.6 | 0.123 | 9 | 47.7 | 3.25 |
| stress | periodic 10 ms | 99.6 | 0.203 | 11.3 | 16.3 | 1.91 |
| stress | periodic 50 ms | 29.9 | 0.676 | 12.3 | 12 | 2.25 |
| stress | periodic 200 ms | 14.4 | 2.154 | 10.3 | 10.3 | 2.65 |

## 3. Victim selection policies

| scenario | policy | aborts | wasted_work_s | throughput_per_s | max_aborts_one_task | avg_victim_priority | avg_task_priority |
|---|---|---|---|---|---|---|---|
| bank | lowest_priority | 29.2 | 3.961 | 111.6 | 3 | 1.76 | 4.28 |
| bank | least_work | 35.8 | 4.419 | 104.9 | 3 | 4.62 | 4.28 |
| bank | most_resources | 31.8 | 6.038 | 107.6 | 1.8 | 4.39 | 4.28 |
| bank | weighted_raw | 24 | 3.574 | 120.6 | 2.6 | 2.23 | 4.28 |
| bank | weighted | 21.2 | 2.633 | 127.1 | 2.6 | 2.42 | 4.28 |
| philosophers | lowest_priority | 10.2 | 1.175 | 51.1 | 1 | 0 | 0 |
| philosophers | least_work | 6.8 | 0.235 | 53.1 | 2.6 | 0 | 0 |
| philosophers | most_resources | 8.2 | 0.93 | 55.4 | 1 | 0 | 0 |
| philosophers | weighted_raw | 12 | 1.448 | 50.9 | 1.2 | 0 | 0 |
| philosophers | weighted | 12.4 | 1.518 | 50.4 | 1.4 | 0 | 0 |
| stress | lowest_priority | 8.6 | 0.248 | 172.3 | 1.8 | 3.28 | 5.45 |
| stress | least_work | 9 | 0.267 | 142.7 | 2.4 | 5.84 | 5.45 |
| stress | most_resources | 10 | 0.339 | 154.2 | 2.4 | 5.2 | 5.45 |
| stress | weighted_raw | 10.6 | 0.341 | 159.0 | 2 | 4.21 | 5.45 |
| stress | weighted | 9.8 | 0.248 | 166.8 | 2.4 | 5 | 5.45 |

## 4. Prevention vs detection + recovery

| transfers | approach | throughput_per_s | wall_time_s | aborts | wasted_work_s |
|---|---|---|---|---|---|
| 20 | detection + recovery | 149.0 | 0.134 | 4 | 0.099 |
| 20 | prevention (lock ordering) | 181.7 | 0.112 | 0 | 0.0 |
| 40 | detection + recovery | 139.6 | 0.288 | 8.3 | 0.432 |
| 40 | prevention (lock ordering) | 161.8 | 0.249 | 0 | 0.0 |
| 80 | detection + recovery | 96.9 | 0.834 | 59 | 12.42 |
| 80 | prevention (lock ordering) | 135.3 | 0.595 | 0 | 0.0 |
| 160 | detection + recovery | 74.6 | 2.151 | 163 | 83.864 |
| 160 | prevention (lock ordering) | 98.2 | 1.631 | 0 | 0.0 |
