# NAS 挂载说明

## SMB 连接

```bash
# 挂载
mount -t smbfs //<USER>:<PASS>@<NAS>/<SHARE> /<NAS_MOUNT>

# NAS 上的项目路径（通过 SMB）
/<NAS_MOUNT>/<NAS_PROJECT_PATH>/

# NAS 上的实际路径
/<NAS_VOLUME>/<NAS_PROJECT_PATH>/
```

## 同步方向

本地 → NAS：写卡 + 信源缓存。NAS GPU 专注推理。
```bash
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "<PROJECT_ROOT>/" \
  "/<NAS_MOUNT>/<NAS_PROJECT_PATH>/"
```
