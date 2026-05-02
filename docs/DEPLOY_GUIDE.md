# 柠优生活大数据平台 · 全容器部署指南

> 适用于阿里云 ECS / 腾讯云 CVM / AWS EC2 等 Linux 云服务器  
> 策略：前端 + 后端 + MySQL + Redis + PostgreSQL 全部 Docker 容器化

---

## 一、服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| **CPU** | 2 核 | 4 核 |
| **内存** | 4 GB | 8 GB |
| **磁盘** | 40 GB SSD | 80 GB SSD |
| **系统** | Ubuntu 22.04 / CentOS 8+ | Ubuntu 22.04 LTS |
| **带宽** | 3 Mbps | 5 Mbps |

---

## 二、安装 Docker（如已安装可跳过）

```bash
# Ubuntu
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 验证
docker --version
docker compose version
```

---

## 三、上传代码到服务器

### 方式 A: Git 拉取（推荐）
```bash
cd /opt
git clone <你的仓库地址> lnys
cd lnys
```

### 方式 B: 本地打包上传
```bash
# 本地执行（排除 node_modules 等）
tar czf lnys.tar.gz --exclude=node_modules --exclude=.venv --exclude=__pycache__ -C /path/to nyshdsjpt
scp lnys.tar.gz root@<服务器IP>:/opt/

# 服务器执行
cd /opt && tar xzf lnys.tar.gz && mv nyshdsjpt lnys
```

---

## 四、配置环境变量

```bash
cd /opt/lnys

# 从模板创建生产环境配置
cp .env.prod.example .env.prod

# 编辑填写真实值
vim .env.prod
```

**必须修改的字段：**
```
DB_PASSWORD=<MySQL 用户密码>
MYSQL_ROOT_PASSWORD=<MySQL root 密码>
REDIS_PASSWORD=<Redis 密码>
POSTGRES_PASSWORD=<PostgreSQL 密码>
SECRET_KEY=<至少32字符的随机密钥>
LLM_API_KEY=<LLM API Key>
ALLOWED_ORIGINS=http://<你的域名或IP>
```

生成随机密钥：
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 五、一键启动

```bash
cd /opt/lnys

# 构建并启动所有容器（首次约 5-15 分钟）
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

# 查看容器状态
docker compose --env-file .env.prod -f docker-compose.prod.yml ps

# 查看后端日志
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend
```

等待所有容器 `healthy` / `running` 后，访问 `http://<服务器IP>` 即可使用。

---

## 六、MySQL 调优（可选但推荐）

```bash
# 进入 MySQL 容器调优连接数
docker compose --env-file .env.prod -f docker-compose.prod.yml exec mysql \
  mysql -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env.prod | cut -d= -f2)" -e "
    SET GLOBAL max_connections = 512;
    SET GLOBAL wait_timeout = 600;
    SET GLOBAL interactive_timeout = 600;
    SET GLOBAL thread_cache_size = 64;
  "
```

---

## 七、验证部署

```bash
# 1. 后端健康检查
curl http://localhost/api/health

# 2. 前端页面
curl -I http://localhost

# 3. 容器状态
docker compose --env-file .env.prod -f docker-compose.prod.yml ps

# 期望输出：
# frontend   running  0.0.0.0:80->80/tcp
# backend    healthy  8000/tcp
# mysql      healthy  3306/tcp
# redis      running  6379/tcp
# postgres   healthy  5432/tcp
```

---

## 八、日常运维

### 查看日志
```bash
# 后端日志
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend

# 全部日志
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f --tail=100
```

### 重启服务
```bash
# 仅重启后端
docker compose --env-file .env.prod -f docker-compose.prod.yml restart backend

# 重启全部
docker compose --env-file .env.prod -f docker-compose.prod.yml restart
```

### 更新部署
```bash
cd /opt/lnys
git pull

# 重新构建并启动（仅重建有变化的镜像）
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

### 停止服务
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml down

# 停止并删除数据卷（⚠️ 会丢失数据库数据！）
docker compose --env-file .env.prod -f docker-compose.prod.yml down -v
```

### 数据库备份
```bash
# MySQL 备份
docker compose --env-file .env.prod -f docker-compose.prod.yml exec mysql \
  mysqldump -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env.prod | cut -d= -f2)" lnys_db \
  > backup_$(date +%Y%m%d_%H%M%S).sql

# PostgreSQL 备份
docker compose --env-file .env.prod -f docker-compose.prod.yml exec postgres \
  pg_dump -U lnys_user lnys_checkpoint \
  > pg_backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 九、HTTPS 配置（可选）

如需 HTTPS，推荐使用 Certbot + Nginx 反向代理：

```bash
# 安装 certbot（宿主机）
apt install -y certbot python3-certbot-nginx

# 先将 docker-compose.prod.yml 中 frontend ports 改为 8080:80
# 然后在宿主机安装 nginx 做 HTTPS 终端

# 申请证书
certbot --nginx -d your-domain.com
```

---

## 十、故障排查

| 症状 | 排查方法 |
|------|---------|
| 前端白屏 | `docker logs <frontend容器>` 查 nginx 错误 |
| API 502 | `docker logs <backend容器>` 查后端是否启动 |
| 数据库连不上 | `docker compose ps` 确认 mysql 状态为 healthy |
| 容器反复重启 | `docker logs <容器名>` 查启动报错 |
| 内存不足 | `free -h` + `docker stats` 检查内存使用 |
