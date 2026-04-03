-- ════════════════════════════════════════════════════════════
--  柠优生活大数据平台 · MySQL 建表脚本
--  对应 方案_06 § 0.4 MySQL 数据库建表
-- ════════════════════════════════════════════════════════════
SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS lnys_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lnys_db;

-- ── SKU 商品表 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skus (
    sku_code    VARCHAR(20)    PRIMARY KEY COMMENT 'SKU编码，如 LY-GR-001',
    name        VARCHAR(100)   NOT NULL    COMMENT '商品名称',
    category    VARCHAR(50)    NOT NULL    COMMENT '品类',
    unit_price  DECIMAL(10,2)  NOT NULL    COMMENT '零售单价（元）',
    season_tag  VARCHAR(20)    DEFAULT NULL COMMENT '季节标签'
) ENGINE=InnoDB COMMENT='商品SKU表';

-- ── 门店表 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stores (
    store_id   VARCHAR(10)   PRIMARY KEY COMMENT '门店编号，如 NDE-001',
    name       VARCHAR(100)  NOT NULL,
    city       VARCHAR(50)   NOT NULL,
    province   VARCHAR(50)   NOT NULL,
    tier       VARCHAR(10)   NOT NULL COMMENT '一线/二线/三线'
) ENGINE=InnoDB COMMENT='线下门店表';

-- ── 客户档案表 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    customer_id    VARCHAR(20)   PRIMARY KEY COMMENT '客户ID，如 LY000001',
    name           VARCHAR(100)  DEFAULT NULL,
    phone          VARCHAR(20)   DEFAULT NULL,
    city           VARCHAR(50)   DEFAULT NULL,
    province       VARCHAR(50)   DEFAULT NULL,
    member_level   ENUM('普通','银卡','金卡','钻石') DEFAULT '普通',
    register_date  DATE          DEFAULT NULL,
    channel        ENUM('online','offline','both') DEFAULT 'online',
    INDEX idx_member (member_level),
    INDEX idx_city   (city)
) ENGINE=InnoDB COMMENT='客户档案表';

-- ── 订单表 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR(30)   PRIMARY KEY,
    customer_id     VARCHAR(20)   NOT NULL,
    sku_code        VARCHAR(20)   NOT NULL,
    quantity        INT           NOT NULL,
    unit_price      DECIMAL(10,2) NOT NULL,
    total_amount    DECIMAL(12,2) NOT NULL,
    channel         ENUM('online','offline') DEFAULT 'online',
    store_id        VARCHAR(10)   DEFAULT NULL COMMENT '线下门店ID',
    ship_city       VARCHAR(50)   DEFAULT NULL,
    payment_method  VARCHAR(20)   DEFAULT NULL,
    order_date      DATETIME      NOT NULL,
    INDEX idx_customer (customer_id),
    INDEX idx_date     (order_date),
    INDEX idx_sku      (sku_code)
) ENGINE=InnoDB COMMENT='订单明细表';

-- ── 分析结果持久化表 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis_results (
    id            BIGINT        AUTO_INCREMENT PRIMARY KEY,
    module        VARCHAR(50)   NOT NULL COMMENT '模块名：customer/forecast/fraud/...',
    result_json   LONGTEXT      NOT NULL COMMENT 'Agent 输出 JSON',
    generated_at  DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_module (module),
    INDEX idx_time   (generated_at)
) ENGINE=InnoDB COMMENT='Agent分析结果缓存表';

-- ── 欺诈记录表 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fraud_records (
    transaction_id  VARCHAR(40)    PRIMARY KEY,
    risk_score      DECIMAL(5,4)   NOT NULL,
    risk_level      ENUM('低风险','中风险','高风险') NOT NULL,
    rule_triggered  TINYINT(1)     DEFAULT 0,
    detected_at     DATETIME       DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_level (risk_level),
    INDEX idx_time  (detected_at)
) ENGINE=InnoDB COMMENT='欺诈检测记录表';

-- ── 客服对话表 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(64)  NOT NULL,
    role        ENUM('user','bot') NOT NULL,
    content     TEXT         NOT NULL,
    intent      VARCHAR(50)  DEFAULT NULL,
    confidence  DECIMAL(5,4) DEFAULT NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_time    (created_at)
) ENGINE=InnoDB COMMENT='客服对话历史表';

-- ── 库存快照表 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id            BIGINT        AUTO_INCREMENT PRIMARY KEY,
    sku_code      VARCHAR(20)   NOT NULL,
    store_id      VARCHAR(10)   NOT NULL,
    stock_qty     INT           NOT NULL DEFAULT 0,
    reorder_point INT           DEFAULT NULL,
    date          DATE          NOT NULL,
    INDEX idx_sku_store (sku_code, store_id),
    INDEX idx_date      (date)
) ENGINE=InnoDB COMMENT='库存每日快照表';


-- ════════════════════════════════════════════════════════════
--  v4.0 治理表
-- ════════════════════════════════════════════════════════════

-- ── runs：工作流执行记录 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    run_id           CHAR(36)       PRIMARY KEY COMMENT 'UUID',
    thread_id        VARCHAR(128)   NOT NULL    COMMENT 'LangGraph thread_id',
    request_id       VARCHAR(128)   NOT NULL    COMMENT '业务侧 request_id',
    entrypoint       VARCHAR(100)   NOT NULL    COMMENT '调用入口路由',
    workflow_name    VARCHAR(100)   NOT NULL,
    workflow_version VARCHAR(50)    DEFAULT 'latest',
    status           ENUM('pending','running','paused','completed','failed','cancelled') NOT NULL DEFAULT 'pending',
    input_summary    TEXT           DEFAULT NULL,
    output_summary   TEXT           DEFAULT NULL,
    total_tokens     INT            DEFAULT 0,
    total_cost       DECIMAL(10,6)  DEFAULT 0.000000,
    error_message    TEXT           DEFAULT NULL,
    triggered_by     VARCHAR(100)   DEFAULT NULL COMMENT '触发者用户名',
    started_at       DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    ended_at         DATETIME(3)    DEFAULT NULL,
    latency_ms       INT            DEFAULT NULL,
    INDEX idx_runs_request_id    (request_id),
    INDEX idx_runs_thread_id     (thread_id),
    INDEX idx_runs_workflow_name (workflow_name),
    INDEX idx_runs_status        (status),
    INDEX idx_runs_started_at    (started_at)
) ENGINE=InnoDB COMMENT='工作流执行记录';

-- ── run_steps：步骤级执行记录（用于回放与审计）────────────────
CREATE TABLE IF NOT EXISTS run_steps (
    step_id          CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    run_id           CHAR(36)      NOT NULL,
    parent_step_id   CHAR(36)      DEFAULT NULL,
    step_type        ENUM('agent_call','tool_call','service_call','llm_call','hitl','handoff','guardrail') NOT NULL,
    step_name        VARCHAR(100)  NOT NULL,
    agent_name       VARCHAR(100)  DEFAULT NULL,
    tool_name        VARCHAR(100)  DEFAULT NULL,
    model_name       VARCHAR(100)  DEFAULT NULL,
    prompt_id        CHAR(36)      DEFAULT NULL,
    prompt_version   VARCHAR(50)   DEFAULT NULL,
    policy_version   VARCHAR(50)   DEFAULT NULL,
    handoff_from     VARCHAR(100)  DEFAULT NULL,
    handoff_to       VARCHAR(100)  DEFAULT NULL,
    status           ENUM('pending','running','paused','completed','failed','cancelled') NOT NULL DEFAULT 'pending',
    input_summary    TEXT          DEFAULT NULL,
    output_summary   TEXT          DEFAULT NULL,
    guardrail_hits_json  JSON      DEFAULT NULL,
    token_usage_json     JSON      DEFAULT NULL,
    cost_amount      DECIMAL(10,6) DEFAULT 0.000000,
    retry_count      TINYINT       DEFAULT 0,
    artifact_ids_json    JSON      DEFAULT NULL,
    error_message    TEXT          DEFAULT NULL,
    started_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    ended_at         DATETIME(3)   DEFAULT NULL,
    INDEX idx_steps_run_id        (run_id),
    INDEX idx_steps_parent        (parent_step_id),
    INDEX idx_steps_agent         (agent_name),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='步骤级执行记录，用于回放与审计';

-- ── artifacts：产物元数据登记 ─────────────────────────────────
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id   CHAR(36)       PRIMARY KEY COMMENT 'UUID',
    artifact_type VARCHAR(50)    NOT NULL,
    artifact_uri  VARCHAR(500)   NOT NULL   COMMENT '文件路径或对象存储 key',
    content_type  VARCHAR(100)   DEFAULT 'application/json',
    summary       TEXT           DEFAULT NULL,
    metadata_json JSON           DEFAULT NULL,
    run_id        CHAR(36)       DEFAULT NULL,
    step_id       CHAR(36)       DEFAULT NULL,
    created_at    DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_artifacts_run_id (run_id),
    INDEX idx_artifacts_type   (artifact_type)
) ENGINE=InnoDB COMMENT='产物元数据登记表';

-- ── agents：Agent 注册与元信息 ────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    agent_id     CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    agent_name   VARCHAR(100)  NOT NULL UNIQUE,
    description  TEXT          DEFAULT NULL,
    version      VARCHAR(50)   DEFAULT 'latest',
    is_active    TINYINT(1)    DEFAULT 1,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='Agent 注册表';

CREATE TABLE IF NOT EXISTS agent_tools (
    id           BIGINT        AUTO_INCREMENT PRIMARY KEY,
    agent_id     CHAR(36)      NOT NULL,
    tool_name    VARCHAR(100)  NOT NULL,
    description  TEXT          DEFAULT NULL,
    is_active    TINYINT(1)    DEFAULT 1,
    UNIQUE KEY uk_agent_tool (agent_id, tool_name),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Agent 可用工具注册表';

-- ── prompts：Prompt 版本管理 ──────────────────────────────────
CREATE TABLE IF NOT EXISTS prompts (
    prompt_id    CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name         VARCHAR(100)  NOT NULL,
    agent_name   VARCHAR(100)  NOT NULL,
    description  TEXT          DEFAULT NULL,
    content      LONGTEXT      NOT NULL,
    variables    JSON          DEFAULT NULL   COMMENT '模板变量列表',
    tags         JSON          DEFAULT NULL,
    version      INT           NOT NULL DEFAULT 1,
    status       ENUM('draft','reviewing','active','archived') NOT NULL DEFAULT 'draft',
    created_by   VARCHAR(100)  NOT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uq_prompts_name (name),
    INDEX idx_prompts_agent  (agent_name),
    INDEX idx_prompts_status (status)
) ENGINE=InnoDB COMMENT='Prompt 版本管理表';

CREATE TABLE IF NOT EXISTS prompt_releases (
    release_id   CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    prompt_id    CHAR(36)      NOT NULL,
    version      INT           NOT NULL,
    status       ENUM('pending','approved','rejected','rolled_back') NOT NULL DEFAULT 'pending',
    released_by  VARCHAR(100)  NOT NULL,
    approved_by  VARCHAR(100)  DEFAULT NULL,
    note         TEXT          DEFAULT NULL,
    released_at  DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_prompt_releases_prompt (prompt_id),
    FOREIGN KEY (prompt_id) REFERENCES prompts(prompt_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Prompt 发布记录';

-- ── policies：策略与 Guardrail 管理 ─────────────────────────────
CREATE TABLE IF NOT EXISTS policies (
    policy_id    CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name         VARCHAR(100)  NOT NULL UNIQUE,
    policy_type  VARCHAR(50)   NOT NULL   COMMENT 'input_guard/output_guard/route_guard/tool_guard',
    description  TEXT          DEFAULT NULL,
    rules_json   JSON          NOT NULL   COMMENT '策略规则定义',
    version      INT           NOT NULL DEFAULT 1,
    status       ENUM('draft','active','archived') NOT NULL DEFAULT 'draft',
    created_by   VARCHAR(100)  NOT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='Guardrail 与 Policy 管理表';

-- ── releases：发布批次管理（Release Center）─────────────────────
CREATE TABLE IF NOT EXISTS releases (
    release_id   CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name         VARCHAR(200)  NOT NULL,
    release_type VARCHAR(50)   NOT NULL   COMMENT 'prompt/policy/workflow/config',
    version      VARCHAR(50)   NOT NULL,
    status       ENUM('draft','in_review','released','rolled_back','failed') NOT NULL DEFAULT 'draft',
    released_by  VARCHAR(100)  NOT NULL,
    approved_by  VARCHAR(100)  DEFAULT NULL,
    note         TEXT          DEFAULT NULL,
    released_at  DATETIME(3)   DEFAULT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_releases_status (status),
    INDEX idx_releases_type   (release_type)
) ENGINE=InnoDB COMMENT='发布批次管理表';

CREATE TABLE IF NOT EXISTS release_items (
    id           BIGINT        AUTO_INCREMENT PRIMARY KEY,
    release_id   CHAR(36)      NOT NULL,
    item_type    VARCHAR(50)   NOT NULL   COMMENT 'prompt/policy/workflow/config',
    item_id      CHAR(36)      NOT NULL,
    item_name    VARCHAR(200)  NOT NULL,
    from_version VARCHAR(50)   DEFAULT NULL,
    to_version   VARCHAR(50)   NOT NULL,
    INDEX idx_release_items_release (release_id),
    FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='发布批次明细表';

CREATE TABLE IF NOT EXISTS release_rollbacks (
    id             BIGINT       AUTO_INCREMENT PRIMARY KEY,
    release_id     CHAR(36)     NOT NULL,
    rollback_by    VARCHAR(100) NOT NULL,
    target_version VARCHAR(50)  NOT NULL,
    reason         TEXT         DEFAULT NULL,
    result_summary TEXT         DEFAULT NULL,
    approval_id    CHAR(36)     DEFAULT NULL,
    executed_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='发布回滚记录表';

-- ── eval 评测体系 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_datasets (
    dataset_id   CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name         VARCHAR(100)  NOT NULL UNIQUE,
    description  TEXT          DEFAULT NULL,
    task_type    VARCHAR(50)   NOT NULL   COMMENT 'routing/qa/risk_scoring/...',
    item_count   INT           DEFAULT 0,
    created_by   VARCHAR(100)  NOT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='评测数据集';

CREATE TABLE IF NOT EXISTS eval_cases (
    case_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    dataset_id   CHAR(36)      NOT NULL,
    input_json   JSON          NOT NULL,
    expected_json JSON         NOT NULL,
    tags         JSON          DEFAULT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    FOREIGN KEY (dataset_id) REFERENCES eval_datasets(dataset_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='评测用例';

CREATE TABLE IF NOT EXISTS evaluators (
    evaluator_id  CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    name          VARCHAR(100) NOT NULL UNIQUE,
    description   TEXT         DEFAULT NULL,
    task_type     VARCHAR(50)  NOT NULL,
    scoring_rules JSON         NOT NULL,
    version       INT          DEFAULT 1,
    created_by    VARCHAR(100) NOT NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='评测器定义表';

CREATE TABLE IF NOT EXISTS eval_experiments (
    experiment_id CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    name          VARCHAR(100) NOT NULL,
    agent_name    VARCHAR(100) DEFAULT NULL COMMENT '智能体名称',
    dataset_id    CHAR(36)     NOT NULL,
    evaluator_id  CHAR(36)     NOT NULL,
    target_type   VARCHAR(50)  DEFAULT NULL  COMMENT 'prompt/workflow/agent',
    target_id     CHAR(36)     DEFAULT NULL,
    target_version VARCHAR(50) DEFAULT NULL,
    status        ENUM('pending','running','completed','failed') NOT NULL DEFAULT 'pending',
    total_cases   INT          DEFAULT 0,
    pass_rate     DECIMAL(5,4) DEFAULT NULL COMMENT '通过率 0~1',
    created_by    VARCHAR(100) NOT NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    ended_at      DATETIME(3)  DEFAULT NULL,
    FOREIGN KEY (dataset_id)   REFERENCES eval_datasets(dataset_id),
    FOREIGN KEY (evaluator_id) REFERENCES evaluators(evaluator_id)
) ENGINE=InnoDB COMMENT='评测实验';

CREATE TABLE IF NOT EXISTS eval_results (
    id            BIGINT       AUTO_INCREMENT PRIMARY KEY,
    experiment_id CHAR(36)     NOT NULL,
    case_id       CHAR(36)     NOT NULL,
    actual_json   JSON         NOT NULL,
    score         DECIMAL(5,4) DEFAULT NULL,
    passed        TINYINT(1)   DEFAULT NULL,
    detail_json   JSON         DEFAULT NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    FOREIGN KEY (experiment_id) REFERENCES eval_experiments(experiment_id) ON DELETE CASCADE,
    UNIQUE KEY uq_result_exp_case (experiment_id, case_id)
) ENGINE=InnoDB COMMENT='评测结果明细';

CREATE TABLE IF NOT EXISTS eval_online_samples (
    id            BIGINT       AUTO_INCREMENT PRIMARY KEY,
    import_batch  VARCHAR(64)  NOT NULL    COMMENT '导入批次标识',
    source_run_id CHAR(36)     DEFAULT NULL,
    input_json    JSON         NOT NULL,
    label_json    JSON         DEFAULT NULL,
    source_note   TEXT         DEFAULT NULL,
    imported_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='线上抽样样本表';

-- ── review_cases + review_actions：HITL 审核 ──────────────────
CREATE TABLE IF NOT EXISTS review_cases (
    case_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    run_id       CHAR(36)      NOT NULL,
    step_id      CHAR(36)      DEFAULT NULL,
    review_type  VARCHAR(50)   NOT NULL,
    priority     ENUM('low','medium','high','critical') NOT NULL DEFAULT 'high',
    status       ENUM('pending','in_review','approved','edited','rejected','expired') NOT NULL DEFAULT 'pending',
    subject      VARCHAR(500)  NOT NULL,
    context_json JSON          DEFAULT NULL,
    created_by   VARCHAR(100)  NOT NULL DEFAULT 'system',
    assigned_to  VARCHAR(100)  DEFAULT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_review_cases_status  (status),
    INDEX idx_review_cases_run_id  (run_id),
    INDEX idx_review_cases_type    (review_type)
) ENGINE=InnoDB COMMENT='HITL 审核案例表';

CREATE TABLE IF NOT EXISTS review_actions (
    action_id        CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    case_id          CHAR(36)     NOT NULL,
    action_type      ENUM('approve','edit','reject','reassign','comment') NOT NULL,
    decision_by      VARCHAR(100) NOT NULL,
    decision_note    TEXT         DEFAULT NULL,
    override_payload JSON         DEFAULT NULL,
    created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_review_actions_case (case_id),
    FOREIGN KEY (case_id) REFERENCES review_cases(case_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='HITL 审核动作记录';

-- ── audit_logs：操作审计 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id           BIGINT        AUTO_INCREMENT PRIMARY KEY,
    operator     VARCHAR(100)  NOT NULL,
    action       VARCHAR(100)  NOT NULL   COMMENT '操作名称',
    target_type  VARCHAR(50)   NOT NULL   COMMENT '操作对象类型',
    target_id    VARCHAR(128)  NOT NULL,
    before_json  JSON          DEFAULT NULL,
    after_json   JSON          DEFAULT NULL,
    ip_address   VARCHAR(50)   DEFAULT NULL,
    user_agent   VARCHAR(500)  DEFAULT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_audit_target_id  (target_id),
    INDEX idx_audit_operator   (operator),
    INDEX idx_audit_created_at (created_at)
) ENGINE=InnoDB COMMENT='操作审计日志';

-- ── action_ledgers：高风险操作幂等账本 ───────────────────────
CREATE TABLE IF NOT EXISTS action_ledgers (
    id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
    action_type      VARCHAR(100)  NOT NULL    COMMENT '操作类型',
    target_type      VARCHAR(50)   NOT NULL,
    target_id        VARCHAR(128)  NOT NULL,
    idempotency_key  VARCHAR(256)  NOT NULL UNIQUE COMMENT '幂等键',
    requested_by     VARCHAR(100)  NOT NULL,
    approved_by      VARCHAR(100)  DEFAULT NULL,
    status           ENUM('pending','approved','executing','completed','failed','rejected') NOT NULL DEFAULT 'pending',
    result_summary   TEXT          DEFAULT NULL,
    payload_json     JSON          DEFAULT NULL,
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_action_ledgers_key    (idempotency_key),
    INDEX idx_action_ledgers_status (status),
    INDEX idx_action_ledgers_type   (action_type)
) ENGINE=InnoDB COMMENT='高风险操作幂等账本';

-- ── faq_documents：知识库 FAQ ─────────────────────────────────
CREATE TABLE IF NOT EXISTS faq_documents (
    doc_id       CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    group_name   VARCHAR(100)  NOT NULL    COMMENT '知识分组',
    title        VARCHAR(500)  NOT NULL,
    content      LONGTEXT      NOT NULL,
    source       VARCHAR(200)  DEFAULT NULL COMMENT '来源说明',
    is_active    TINYINT(1)    NOT NULL DEFAULT 1,
    created_by   VARCHAR(100)  NOT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_faq_group    (group_name),
    INDEX idx_faq_active   (is_active)
) ENGINE=InnoDB COMMENT='知识库 FAQ 文档表';

-- ── memory_records：用户长期记忆（仅 OpenClaw）────────────────
CREATE TABLE IF NOT EXISTS memory_records (
    memory_id        CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    customer_id      VARCHAR(20)  NOT NULL,
    memory_kind      ENUM('semantic','episodic') NOT NULL DEFAULT 'semantic',
    source_type      VARCHAR(50)  NOT NULL    COMMENT 'agent/human/import',
    source_run_id    CHAR(36)     DEFAULT NULL,
    source_message_id VARCHAR(128) DEFAULT NULL,
    content_summary  TEXT         NOT NULL,
    risk_level       ENUM('low','medium','high') NOT NULL DEFAULT 'low',
    pii_flag         TINYINT(1)   NOT NULL DEFAULT 0,
    expires_at       DATETIME(3)  DEFAULT NULL,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    validated_by     VARCHAR(100) DEFAULT NULL,
    feedback_score   TINYINT      DEFAULT NULL COMMENT '-1/0/1',
    importance       FLOAT        DEFAULT 0.5 COMMENT 'memory importance score 0-1',
    created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_memory_customer  (customer_id),
    INDEX idx_memory_active    (is_active),
    INDEX idx_memory_expires   (expires_at)
) ENGINE=InnoDB COMMENT='用户长期记忆表（仅 OpenClaw 使用）';

CREATE TABLE IF NOT EXISTS memory_feedback (
    id            BIGINT       AUTO_INCREMENT PRIMARY KEY,
    memory_id     CHAR(36)     NOT NULL,
    feedback_type ENUM('disable','expire','flag_pii','human_review','auto') NOT NULL,
    reason        TEXT         DEFAULT NULL,
    operated_by   VARCHAR(100) NOT NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    FOREIGN KEY (memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='记忆治理反馈表';


-- ════════════════════════════════════════════════════════════
--  v4.0 RBAC 基础表
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    user_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    username     VARCHAR(100)  NOT NULL UNIQUE,
    display_name VARCHAR(200)  DEFAULT NULL,
    email        VARCHAR(200)  DEFAULT NULL,
    hashed_pw    VARCHAR(256)  NOT NULL,
    is_active    TINYINT(1)    NOT NULL DEFAULT 1,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='后台用户表';

CREATE TABLE IF NOT EXISTS roles (
    role_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    role_name    VARCHAR(100)  NOT NULL UNIQUE
        COMMENT 'platform_admin/ml_engineer/ops_analyst/customer_service_manager/risk_reviewer/auditor',
    description  TEXT          DEFAULT NULL,
    created_at   DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB COMMENT='角色表';

CREATE TABLE IF NOT EXISTS permissions (
    perm_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    perm_code    VARCHAR(200)  NOT NULL UNIQUE COMMENT '如 admin:traces:read',
    description  TEXT          DEFAULT NULL
) ENGINE=InnoDB COMMENT='权限码表';

CREATE TABLE IF NOT EXISTS user_roles (
    id         BIGINT       AUTO_INCREMENT PRIMARY KEY,
    user_id    CHAR(36)     NOT NULL,
    role_id    CHAR(36)     NOT NULL,
    granted_by VARCHAR(100) NOT NULL,
    granted_at DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_user_role (user_id, role_id),
    INDEX idx_user_roles_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)   ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='用户-角色关联表';

CREATE TABLE IF NOT EXISTS role_permissions (
    id        BIGINT       AUTO_INCREMENT PRIMARY KEY,
    role_id   CHAR(36)     NOT NULL,
    perm_id   CHAR(36)     NOT NULL,
    UNIQUE KEY uk_role_perm (role_id, perm_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id)       ON DELETE CASCADE,
    FOREIGN KEY (perm_id) REFERENCES permissions(perm_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='角色-权限关联表';


-- ── 预置角色种子数据 ─────────────────────────────────────────
INSERT IGNORE INTO roles (role_id, role_name, description) VALUES
    (UUID(), 'platform_admin',            '平台超级管理员'),
    (UUID(), 'ml_engineer',               '算法/模型开发工程师'),
    (UUID(), 'ops_analyst',               '运营分析师'),
    (UUID(), 'customer_service_manager',  '客服主管'),
    (UUID(), 'risk_reviewer',             '风控审核员'),
    (UUID(), 'auditor',                   '审计只读员');


-- ════════════════════════════════════════════════════════════
--  v5.0 知识库中台
-- ════════════════════════════════════════════════════════════

-- ── kb_libraries：知识库实例 ──────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_libraries (
    kb_id            CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name             VARCHAR(200)  NOT NULL UNIQUE COMMENT '唯一标识名',
    display_name     VARCHAR(200)  NOT NULL COMMENT '显示名称',
    description      TEXT          DEFAULT NULL,
    domain           VARCHAR(50)   NOT NULL DEFAULT 'enterprise' COMMENT '业务域',
    collection_name  VARCHAR(100)  NOT NULL UNIQUE COMMENT 'ChromaDB collection',
    embedding_model  VARCHAR(200)  NOT NULL DEFAULT 'bge-small-zh-v1.5',
    chunk_strategy   VARCHAR(50)   NOT NULL DEFAULT 'recursive' COMMENT 'recursive/fixed/none',
    chunk_config     JSON          DEFAULT NULL COMMENT '分块参数',
    doc_count        INT           NOT NULL DEFAULT 0 COMMENT '文档总数(冗余)',
    chunk_count      INT           NOT NULL DEFAULT 0 COMMENT '分块总数(冗余)',
    is_active        TINYINT(1)    NOT NULL DEFAULT 1,
    created_by       VARCHAR(100)  NOT NULL,
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_kb_lib_domain  (domain),
    INDEX idx_kb_lib_active  (is_active)
) ENGINE=InnoDB COMMENT='知识库实例表';

-- ── kb_documents：文档 ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_documents (
    document_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    kb_id            CHAR(36)      NOT NULL,
    title            VARCHAR(500)  NOT NULL,
    source_type      VARCHAR(50)   NOT NULL DEFAULT 'faq_manual' COMMENT 'faq_manual/file_upload/agent_auto/api_import',
    source_uri       VARCHAR(500)  DEFAULT NULL COMMENT '文件路径/URL',
    file_name        VARCHAR(300)  DEFAULT NULL,
    file_type        VARCHAR(50)   DEFAULT NULL COMMENT 'pdf/docx/xlsx/csv/txt/image',
    file_size        BIGINT        DEFAULT NULL COMMENT '字节数',
    file_hash        VARCHAR(64)   DEFAULT NULL COMMENT 'SHA-256',
    content_raw      LONGTEXT      DEFAULT NULL COMMENT '原始提取文本',
    content_clean    LONGTEXT      DEFAULT NULL COMMENT '清洗后文本',
    status           VARCHAR(30)   NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/ready/failed/disabled',
    version          INT           NOT NULL DEFAULT 1,
    quality_score    FLOAT         DEFAULT NULL COMMENT '0~1',
    chunk_count      INT           NOT NULL DEFAULT 0,
    error_msg        TEXT          DEFAULT NULL,
    created_by       VARCHAR(100)  NOT NULL DEFAULT 'system',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_kb_doc_kb     (kb_id),
    INDEX idx_kb_doc_status (status),
    INDEX idx_kb_doc_hash   (file_hash),
    INDEX idx_kb_doc_source (source_type),
    FOREIGN KEY (kb_id) REFERENCES kb_libraries(kb_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库文档表';

-- ── kb_chunks：分块 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id         CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    document_id      CHAR(36)      NOT NULL,
    kb_id            CHAR(36)      NOT NULL COMMENT '冗余FK加速查询',
    chunk_index      INT           NOT NULL COMMENT '块序号',
    content          LONGTEXT      NOT NULL,
    token_count      INT           DEFAULT NULL,
    char_count       INT           DEFAULT NULL,
    heading_path     VARCHAR(500)  DEFAULT NULL COMMENT '标题层级路径',
    chunk_type       VARCHAR(30)   NOT NULL DEFAULT 'paragraph' COMMENT 'paragraph/table/list/code/ocr',
    metadata_extra   JSON          DEFAULT NULL,
    chromadb_id      VARCHAR(200)  DEFAULT NULL COMMENT 'ChromaDB 向量 ID',
    embedding_status VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending/done/failed',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_kb_chunk_doc   (document_id),
    INDEX idx_kb_chunk_kb    (kb_id),
    INDEX idx_kb_chunk_embed (embedding_status),
    FOREIGN KEY (document_id) REFERENCES kb_documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (kb_id) REFERENCES kb_libraries(kb_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库分块表';

-- ── kb_document_versions：文档版本快照 ─────────────────────────
CREATE TABLE IF NOT EXISTS kb_document_versions (
    version_id       CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    document_id      CHAR(36)      NOT NULL,
    version          INT           NOT NULL COMMENT '版本号',
    content_raw      LONGTEXT      DEFAULT NULL,
    content_clean    LONGTEXT      DEFAULT NULL,
    quality_score    FLOAT         DEFAULT NULL,
    chunk_count      INT           NOT NULL DEFAULT 0,
    created_by       VARCHAR(100)  NOT NULL DEFAULT 'system',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_kb_ver_doc (document_id, version),
    FOREIGN KEY (document_id) REFERENCES kb_documents(document_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库文档版本快照表';

-- ── kb_feedback：§3.4 用户反馈表 ─────────────────────────────
CREATE TABLE IF NOT EXISTS kb_feedback (
    feedback_id   BIGINT       AUTO_INCREMENT PRIMARY KEY,
    trace_id      VARCHAR(64)  DEFAULT NULL COMMENT '关联到原 answer/search 的 trace_id',
    user_id       VARCHAR(100) NOT NULL     COMMENT '反馈用户 username',
    kb_id         CHAR(36)     DEFAULT NULL COMMENT '命中的主 kb_id（取 hits[0].kb_id）',
    query         TEXT         NOT NULL     COMMENT '原始 query',
    answer        TEXT         DEFAULT NULL COMMENT 'RAG 答案文本（仅 RAG 场景填）',
    citations     JSON         DEFAULT NULL COMMENT 'hits 引用 [{document_id,chunk_id,kb_id,title,score}]',
    rating        TINYINT      NOT NULL     COMMENT '1=👍  -1=👎  0=中性',
    rating_reason VARCHAR(50)  DEFAULT NULL COMMENT 'inaccurate/irrelevant/outdated/incomplete/other',
    free_text     VARCHAR(1000) DEFAULT NULL COMMENT '用户自由文本',
    source        VARCHAR(20)  NOT NULL DEFAULT 'biz_kb'
                                        COMMENT 'biz_kb / admin_kb / copilot_biz_rag / api_external',
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_rating_time (rating, created_at),
    INDEX idx_kb_time     (kb_id, created_at),
    INDEX idx_user_trace  (user_id, trace_id),
    INDEX idx_source      (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='§3.4 KB 用户反馈表（显式 + 后续 self-monitor 自动）';

-- ── 预置知识库种子 ───────────────────────────────────────────
INSERT IGNORE INTO kb_libraries (kb_id, name, display_name, description, domain, collection_name, chunk_strategy, chunk_config, created_by) VALUES
    (UUID(), 'enterprise_faq', '企业FAQ知识库', '客服常见问题解答', 'enterprise', 'kb_ent_faq', 'fixed', '{"max_chars":400,"overlap":100}', 'system'),
    (UUID(), 'sentiment_reviews', '舆情评论知识库', '舆情分析结果向量化存储', 'sentiment', 'sentiment_reviews', 'none', NULL, 'system');

-- ════════════════════════════════════════════════════════════
--  v5.1 Copilot 系统表
--  包含：对话线程、消息、操作审计、记忆、规则、权限覆盖、飞书群映射
-- ════════════════════════════════════════════════════════════

-- ── copilot_threads：对话线程 ────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_threads (
    id           VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    user_id      VARCHAR(64) NOT NULL,
    mode         ENUM('ops', 'biz') NOT NULL COMMENT '运维/运营模式',
    title        VARCHAR(256) NULL COMMENT '自动生成标题',
    status       ENUM('active', 'archived', 'deleted') DEFAULT 'active',
    summary      TEXT NULL COMMENT 'LLM 自动摘要',
    page_origin  VARCHAR(256) NULL COMMENT '发起对话时所在页面',
    tags         JSON NULL COMMENT '标签',
    pinned       BOOLEAN DEFAULT FALSE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_mode (user_id, mode, status),
    INDEX idx_updated (updated_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot 对话线程';

-- ── copilot_messages：对话消息（完整审计）────────────────────
CREATE TABLE IF NOT EXISTS copilot_messages (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id    VARCHAR(36) NOT NULL,
    role         ENUM('user', 'assistant', 'system', 'tool') NOT NULL,
    content      TEXT NOT NULL,
    intent       VARCHAR(64) NULL,
    skills_used  JSON NULL COMMENT '使用的 Skill 列表',
    confidence   FLOAT NULL,
    thinking     TEXT NULL COMMENT '思维链内容',
    artifacts    JSON NULL COMMENT 'Artifact 数据',
    tool_calls   JSON NULL COMMENT '工具调用详情',
    suggestions  JSON NULL COMMENT '建议的后续问题/操作',
    actions_taken JSON NULL COMMENT '执行的操作记录',
    feedback     TINYINT NULL COMMENT '1=👍 -1=👎',
    feedback_text VARCHAR(512) NULL,
    elapsed_ms   INT NULL,
    token_usage  JSON NULL COMMENT '{"input": N, "output": M}',
    source       ENUM('web', 'feishu', 'api', 'scheduler') DEFAULT 'web',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_thread (thread_id, created_at),
    INDEX idx_feedback (feedback),
    INDEX idx_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot 对话消息';

-- ── copilot_action_log：操作审计日志（不可变）────────────────
CREATE TABLE IF NOT EXISTS copilot_action_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id    VARCHAR(36) NOT NULL,
    message_id   BIGINT NOT NULL,
    user_id      VARCHAR(64) NOT NULL,
    action_type  VARCHAR(64) NOT NULL COMMENT 'feishu_notify/export_report/...',
    target       VARCHAR(256) NOT NULL COMMENT '目标（群ID/用户ID/文件路径）',
    payload      JSON NULL,
    status       ENUM('pending', 'approved', 'executed', 'failed', 'rejected', 'pending_approval') NOT NULL,
    result       JSON NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_at  DATETIME NULL,
    INDEX idx_thread (thread_id),
    INDEX idx_user (user_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot 操作审计日志';

-- ── copilot_memory：动态记忆 ────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_memory (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id      VARCHAR(64) NOT NULL,
    domain       VARCHAR(64) NOT NULL COMMENT 'user_preferences/business_context/decisions/patterns',
    title        VARCHAR(256) NOT NULL,
    content      TEXT NOT NULL COMMENT 'Markdown 格式',
    importance   FLOAT DEFAULT 0.5 COMMENT '0~1 重要度',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active    BOOLEAN DEFAULT TRUE COMMENT '软删除',
    INDEX idx_user_domain (user_id, domain),
    INDEX idx_importance (importance DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot 动态记忆';

-- ── copilot_rules：静态规则 ─────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_rules (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope        ENUM('global', 'ops', 'biz') NOT NULL COMMENT '适用范围',
    title        VARCHAR(256) NOT NULL,
    content      TEXT NOT NULL,
    priority     INT DEFAULT 0 COMMENT '高优先级先加载',
    created_by   VARCHAR(64) NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_scope (scope, priority DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot 静态规则';

-- ── copilot_skill_overrides：Skill 权限覆盖 ────────────────
CREATE TABLE IF NOT EXISTS copilot_skill_overrides (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id      VARCHAR(64) NOT NULL,
    skill_name   VARCHAR(64) NOT NULL,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by   VARCHAR(64) NOT NULL,
    reason       VARCHAR(256) NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_skill (user_id, skill_name),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Copilot Skill 权限覆盖';

-- ── feishu_group_mapping：飞书群映射 ────────────────────────
CREATE TABLE IF NOT EXISTS feishu_group_mapping (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    group_name      VARCHAR(64) NOT NULL COMMENT 'procurement/ops_alert/biz_daily',
    chat_id         VARCHAR(128) NOT NULL COMMENT '飞书群 chat_id',
    mode            ENUM('ops', 'biz') NOT NULL,
    patrol_enabled  BOOLEAN DEFAULT TRUE,
    description     VARCHAR(256) NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_group_name (group_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='飞书群映射';

-- ── Copilot 种子数据 ────────────────────────────────────────
INSERT IGNORE INTO copilot_rules (scope, title, content, priority, created_by) VALUES
('global', '身份定义', '你是柠优生活大数据智能决策平台的AI助手。你的回答应该准确、专业、有数据支撑。当用户询问你不确定的内容时，明确说明不确定而不是编造。', 100, 'system'),
('global', '语言规则', '默认使用中文回答用户。即使用户用英文提问，也优先用中文回答，除非用户明确要求用英文。代码、技术名词、英文缩写可保留原文。', 95, 'system'),
('global', '输出格式', '使用 Markdown 格式回答。数据分析结果用表格或列表呈现。关键数字用加粗标记。给出分析结论和可操作建议。', 90, 'system'),
('ops', '运维助手角色', '你是运维助手，具有平台全部功能的访问权限。你可以查询系统健康状态、Trace 跟踪、评测结果、Prompt 版本等运维信息。你可以访问所有业务数据。你可以建议执行操作（如发送飞书通知），但需要用户确认。', 80, 'system'),
('biz', '运营助手角色', '你是运营助手，具有业务空间功能的访问权限。你可以访问客户洞察、销售预测、舆情分析、库存优化、关联分析等业务数据。你不能访问系统运维信息。你可以建议执行操作，但需要用户确认。', 80, 'system');

INSERT IGNORE INTO feishu_group_mapping (group_name, chat_id, mode, description) VALUES
('ops_alert', 'oc_063e389803f42620f3791f9db6ed2f72', 'ops', '运维告警群'),
('procurement', 'oc_4468a7fe45b62b783f335cbf1443c7fa', 'biz', '采购协调群'),
('biz_daily', 'oc_2f5f6b97ddd9f1b6273a9cff0c33b708', 'biz', '运营日报群');
