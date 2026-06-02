# 阶段二：信源缓存 + 卡片派发

## 铁律

1. **只用 WebSearch，禁止 WebFetch**（被墙，超时卡死）
2. **URL 必须来自 WebSearch 返回结果**，禁止编造
3. **每卡 2-3 个信源**，中英文各至少一个
4. **缓存写 `data/source_cache/shared/`**，不建子目录
5. **每 20 张存一次盘**，再继续下一批

## 流程

1. 取 pending 种子，按 kw 聚类，B→R→M→Q→F→P→S 优先级，系列内随机
2. 查注册中心命中 → 复用；未命中 → WebSearch
3. WebSearch 结果写 `shared/{类型}_{标题}.md`，格式：`# {title}\n> Source: {url}\n\n{正文}`
4. 注册到 `source_registry/index.json`
5. 创建卡片到 `cards.json`：有信源→ready，required系列无信源→不创建
6. 更新种子 status 为 dispatched
7. 存盘，报告进度

## 禁止

- WebFetch
- 编造 URL
- 写 src/ config/
- 调LLM
- **禁止写 Python 脚本自动化——每张卡片必须亲手搜、亲手写缓存、亲手注册。脚本全跳过搜索步骤，只会批量生产垃圾。**
