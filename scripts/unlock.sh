#!/bin/bash
cd "$(dirname "$0")/.."
find src config -type f -name "*.py" -exec chmod 644 {} + 2>/dev/null
echo "🔓 已解锁"
