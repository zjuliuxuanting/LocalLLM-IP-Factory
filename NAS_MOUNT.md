# NAS 挂载说明

## SMB 连接

```bash
# 挂载
mount -t smbfs //<USER>:<PASS>@<NAS>/work_space /tmp/nas_mount

# NAS 上的项目路径（通过 SMB）
/tmp/nas_mount/workspace_openclaw/喵言汪语/

# NAS 上的实际路径
/volume1/work_space/workspace_openclaw/喵言汪语/
```

## NAS 环境

| 项目 | 值 |
|------|-----|
| NAS 型号 | 绿联 DX4600 |
| IP | <NAS_IP> |
| OpenClaw | :18799 (token: <NAS_TOKEN>) |
| 3080 GPU | <GPU_SERVER_IP>:8080 (qwen35b) |
| 代理 | mihomo @ :7897 |

## 同步方向

本地 Mac → NAS：写卡 + 信源缓存。NAS 3080 专注 GPU 推理。
```bash
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "/Applications/test/创业/显卡妹计划/喵言汪语/" \
  "/tmp/nas_mount/workspace_openclaw/喵言汪语/"
```
