# Scaling and Visit Count Recommendations

This document describes how to tune the KataGo API for different load levels and user counts.

## Visit Count Tradeoff

The `VISITS_QUICK` setting (used for `/suggest` bot moves) directly affects latency and throughput:

| Visits | Latency per move | Throughput (approx) | Use case |
|--------|------------------|---------------------|----------|
| 32 | ~1–2 s | ~3–8 req/s | Default; good balance for most bots |
| 16 | ~0.5–1 s | ~6–15 req/s | High load; slightly weaker play |
| 8 | ~0.3–0.5 s | ~10–25 req/s | Very high load; noticeably weaker play |

**Recommendation:** Start with 32. If you see 503s or high latency under load, reduce to 16. For 100+ concurrent bot players, 16 is often necessary. For 500+, consider 8.

The rank system (`RANKS.md`) already limits bot strength via `humanSLProfile`, so reducing visits mainly affects consistency rather than raw strength—bots will still play at the chosen rank, but moves may vary more.

## Load Scenarios

| Concurrent users | Suggested `VISITS_QUICK` | Notes |
|------------------|--------------------------|-------|
| &lt; 50 | 32 | Default is fine |
| 50–100 | 16–32 | Monitor latency; reduce if needed |
| 100–300 | 16 | Likely need 16 for headroom |
| 300+ | 8–16 | Consider horizontal scaling (more VPSes) |

## Other Settings

- **`KATAGO_MAX_CONCURRENT`**: Limits in-flight analyses per engine. Default 4. Keep ≤ 2× `numSearchThreads` in your KataGo config.
- **`MAX_QUEUE_DEPTH`**: Analysis jobs only. Raised to 30 by default; users can wait for background analysis.
- **`numSearchThreads`** (in `analysis.cfg`): KataGo’s internal parallelism. On 2 CPUs, use 1–2 per engine.
