# deploy/OFFLINE.md
## 离线交付约束
- 运行期零外网拉取：镜像、模型权重、Python 依赖全部随包内置。
- 唯一出网口是 `external_api`（受 Router 数据边界过滤管控，P3 接入），其余全内网闭环。

## 还原步骤（客户内网）
1. `docker load -i dist/images/industriax-images.tar`
2. 把 `dist/models/` 下权重放入 ollama 卷 `/data/industriax/ollama/`
3. `cp deploy/.env.example deploy/.env` 并改密码
4. `docker compose -f deploy/docker-compose.yml up -d`
5. `bash scripts/smoke_health.sh` 验证全绿
