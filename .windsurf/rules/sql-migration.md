---
trigger: glob
globs: backend/db/migrations/**/*.sql
---

# SQL Migration 约束 (改 backend/db/migrations/ 下 SQL 时自动生效)

## 命名遵循项目现有风格

看 `backend/db/migrations/` 已有文件做风格参考, **不要凭空发明 `V<YYYYMMDD>_*.sql` 风格**, 项目实际不用:

| 风格 | 例子 | 用途 |
|---|---|---|
| 版本递增 | `r5_copilot_memory_access.sql` / `r7_kb_feedback.sql` | 常规 release migration |
| 修复 | `fix_fraud_risk_level_charset.sql` | hotfix 字符集 / 字段类型 |
| 模块版本 | `eval_center_v2.sql` | 整模块结构升级 |

新建迁移前先 `git log --oneline -- backend/db/migrations/` 看最新 r 编号, 递增.

## 必须幂等

生产无 staging, 重跑要安全. 所有 ALTER / INSERT / CREATE 都要包"先检查再做":

```sql
-- ALTER TABLE: 先查 information_schema.COLUMNS
SET @col_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'kb_feedback'
    AND COLUMN_NAME = 'created_at'
);
SET @sql = IF(@col_exists = 0,
  'ALTER TABLE kb_feedback ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- INDEX: 先查 information_schema.STATISTICS
SET @idx_exists = (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'kb_feedback'
    AND INDEX_NAME = 'idx_kb_feedback_created_at'
);
SET @sql = IF(@idx_exists = 0,
  'CREATE INDEX idx_kb_feedback_created_at ON kb_feedback(created_at)',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- INSERT: INSERT IGNORE 或 ON DUPLICATE KEY UPDATE
INSERT IGNORE INTO config_keys (k, v) VALUES ('foo', 'bar');
INSERT INTO settings (k, v) VALUES ('mode', 'prod')
  ON DUPLICATE KEY UPDATE v = VALUES(v);
```

## 部署红线 (踩过的坑, 必须遵守)

- **不要走 PowerShell 管道喂 SQL 给 docker exec -i** (中文会变 `?`, 红线 P-04). 必须 `scp` 文件 + `docker cp` 进容器 + 容器内 `mysql ... < /tmp/xx.sql` 或 `SOURCE`
- 文件**必须 LF 行尾** (PowerShell 默认 CRLF, 远端 bash 跑会 `\r: command not found`, 红线 P-07). 写完用 VSCode 右下角切到 LF 再保存
- 配套写 `_apply_<name>.sh` 一次性脚本 (项目根, 已 .gitignore): 转 LF + scp + docker cp + 在容器内 SOURCE + 看 log
- 跑完云端要 `SHOW CREATE TABLE` 验证字段确实生效, 不要只看 exit=0

## 强烈推荐

- 每个 migration 顶部注释里写**反向 SQL**便于紧急回滚 (DROP COLUMN / DROP INDEX / DELETE FROM ... WHERE ...)
- INSERT 数据时附 git short hash 或日期 comment, 便于追溯
- 一个 migration 文件聚焦一个主题; 不要把"改字段 + 加索引 + 灌数据 + 删表"塞一个文件
