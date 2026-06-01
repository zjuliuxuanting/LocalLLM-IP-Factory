# /seed-generate

阶段一：种子生成 + 系列扩展。

## 执行

```bash
python3 scripts/seed_generator.py --target 500
```

## 做什么

1. 检测系列饱和度，饱和则自动提案新系列
2. 检查各系列 pending 种子数，不足时调显卡妹补种
3. 5 维质检，通过则写入 seed_pool.json (status=pending)

## 可写

- seed_pool.json

## 禁止

- src/ config/ 下所有 .py 文件
- cards.json
- source_registry/
- 联网抓信源
