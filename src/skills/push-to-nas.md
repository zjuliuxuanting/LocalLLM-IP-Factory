# /push-to-nas

推送 NAS：完整性校验 + rsync。

## 前置

```bash
mount -t smbfs //<USER>:<PASS>@<NAS>/work_space /tmp/nas_mount
```

## 执行

```bash
python3 scripts/push_to_nas.py
```

## 做什么

1. 遍历 ready 卡片，核每张的 source_files 是否全部存在于本地
2. 不全的 → 标记 pending_source，留在本地
3. 全的 → rsync 推 NAS

## 可写

- cards.json (更新缺信源卡片状态)
- NAS 上的项目目录

## 禁止

- src/ config/ 下所有 .py 文件
- 调显卡妹 / GPU
