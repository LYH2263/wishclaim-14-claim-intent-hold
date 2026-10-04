# Wishclaim · 礼物愿望认领

发布 → 认领暂挂（held，写 hold_until+意向人，禁止并行暂挂）→ 确认转正（claimed+TTL）→ 核销/释放。暂挂过期自动回 open，不写释放台账。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5200 |
| API | 10200 |

```bash
docker compose up --build
pytest backend/app/tests
```

0-1：`wish_comment` / `secret_santa` / `price_cap`。
