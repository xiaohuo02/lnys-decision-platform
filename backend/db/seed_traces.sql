SET NAMES utf8mb4;
-- 种子数据：runs + run_steps
-- 使用 NOW() 相对时间，确保数据始终在 24h dashboard 窗口内
DELETE FROM run_steps WHERE run_id IN ('run_20260402_001','run_20260402_002','run_20260402_003','run_20260402_004','run_20260402_005');
DELETE FROM runs      WHERE run_id IN ('run_20260402_001','run_20260402_002','run_20260402_003','run_20260402_004','run_20260402_005');

INSERT INTO runs (run_id, thread_id, request_id, entrypoint, workflow_name, workflow_version, status, input_summary, output_summary, total_tokens, total_cost, error_message, started_at, ended_at, latency_ms)
VALUES
('run_20260402_001','thread_001','req_001','/api/v1/analyze','business_overview','1.0.0','completed','帮我分析一下最近的经营状况','本次经营分析显示整体运营承压：销售预测环比下降3.2%...',1850,0.120000,NULL, NOW() - INTERVAL 3 HOUR, NOW() - INTERVAL 3 HOUR + INTERVAL 15 SECOND, 15200),
('run_20260402_002','thread_002','req_002','/api/fraud/score','risk_review','1.0.0','completed','审核高风险交易 TXN-2026040201','交易 TXN-2026040201 风险评级: 高 (0.87)，建议冻结',920,0.060000,NULL, NOW() - INTERVAL 2 HOUR, NOW() - INTERVAL 2 HOUR + INTERVAL 9 SECOND, 8700),
('run_20260402_003','thread_003','req_003','/api/v1/analyze','business_overview','1.0.0','failed','生成本周销售报告',NULL,450,0.030000,'SentimentService timeout after 30s', NOW() - INTERVAL 90 MINUTE, NOW() - INTERVAL 90 MINUTE + INTERVAL 5 SECOND, 5100),
('run_20260402_004','thread_004','req_004','/api/chat/send','openclaw_session','1.0.0','completed','查一下订单 ORD-88921 的物流','订单 ORD-88921 已发货，预计明天送达',320,0.020000,NULL, NOW() - INTERVAL 1 HOUR, NOW() - INTERVAL 1 HOUR + INTERVAL 4 SECOND, 4200),
('run_20260402_005','thread_005','req_005','/api/v1/analyze','business_overview','1.0.0','paused','做一份完整的经营洞察报告',NULL,1200,0.080000,'HITL: 风控评分需要人工确认', NOW() - INTERVAL 4 HOUR, NULL, NULL)
ON DUPLICATE KEY UPDATE
  started_at   = VALUES(started_at),
  ended_at     = VALUES(ended_at),
  status       = VALUES(status),
  output_summary = VALUES(output_summary),
  total_tokens = VALUES(total_tokens),
  error_message= VALUES(error_message);

INSERT INTO run_steps (step_id, run_id, step_type, step_name, agent_name, model_name, status, input_summary, output_summary, token_usage_json, cost_amount, retry_count, started_at, ended_at)
VALUES
('step_001','run_20260402_001','service_call','data_preparation','BusinessOverviewWorkflow',NULL,'completed','sources=[orders, customers, fraud, reviews, inventory]','数据准备完成：935,261 行，缺失率 1.5%','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR, NOW() - INTERVAL 3 HOUR + INTERVAL 2 SECOND),
('step_002','run_20260402_001','service_call','customer_intel','BusinessOverviewWorkflow',NULL,'completed','run_id=run_20260402_001','高流失客户 Top10，RFM 分布集中在低频高价值群','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR + INTERVAL 2 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 3 SECOND),
('step_003','run_20260402_001','service_call','sales_forecast','BusinessOverviewWorkflow',NULL,'completed','forecast_days=30','未来 30 天销售预测，环比下降 3.2%','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR + INTERVAL 3 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 4 SECOND),
('step_004','run_20260402_001','service_call','sentiment_intel','BusinessOverviewWorkflow',NULL,'completed','run_id=run_20260402_001','近 7 天负面评价占比 12.3%，主题：物流延误、品质投诉','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR + INTERVAL 4 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 7 SECOND),
('step_005','run_20260402_001','service_call','fraud_scoring','BusinessOverviewWorkflow',NULL,'completed','batch mode','高风险交易 3 笔，待人工审核；中风险 17 笔','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR + INTERVAL 7 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 8 SECOND),
('step_006','run_20260402_001','service_call','inventory','BusinessOverviewWorkflow',NULL,'completed','run_id=run_20260402_001','紧急补货 SKU 23 个，总建议采购金额 185,000','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 3 HOUR + INTERVAL 8 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 10 SECOND),
('step_007','run_20260402_001','agent_call','insight_composer','InsightComposerAgent','qwen-plus','completed','artifact_refs=5, use_mock=false','本次经营分析显示整体运营承压：销售预测环比下降3.2%...','{"total_tokens":743,"prompt_tokens":520,"completion_tokens":223}',0.05,0, NOW() - INTERVAL 3 HOUR + INTERVAL 10 SECOND, NOW() - INTERVAL 3 HOUR + INTERVAL 15 SECOND),

-- run_002: risk_review workflow (3 steps)
('step_010','run_20260402_002','service_call','rule_engine','RiskReviewWorkflow',NULL,'completed','txn_id=TXN-2026040201','规则命中: amount_spike, geo_mismatch; 初评分 0.82','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 2 HOUR, NOW() - INTERVAL 2 HOUR + INTERVAL 2 SECOND),
('step_011','run_20260402_002','agent_call','ml_scoring','FraudScoringAgent','lightgbm','completed','features=[amount,device_age,geo_dist,hour]','LightGBM 评分: 0.87, IsolationForest 异常度: 0.91','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 2 HOUR + INTERVAL 2 SECOND, NOW() - INTERVAL 2 HOUR + INTERVAL 5 SECOND),
('step_012','run_20260402_002','agent_call','risk_decision','RiskDecisionAgent','qwen-plus','completed','rule_score=0.82, ml_score=0.87','交易 TXN-2026040201 风险评级: 高 (0.87)，建议冻结','{"total_tokens":620,"prompt_tokens":410,"completion_tokens":210}',0.04,0, NOW() - INTERVAL 2 HOUR + INTERVAL 5 SECOND, NOW() - INTERVAL 2 HOUR + INTERVAL 9 SECOND),

-- run_003: failed business_overview (2 steps, last one failed)
('step_020','run_20260402_003','service_call','data_preparation','BusinessOverviewWorkflow',NULL,'completed','sources=[orders, customers]','数据准备完成：420,118 行','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 90 MINUTE, NOW() - INTERVAL 90 MINUTE + INTERVAL 2 SECOND),
('step_021','run_20260402_003','service_call','sentiment_intel','BusinessOverviewWorkflow',NULL,'failed','run_id=run_20260402_003',NULL,'{"total_tokens":450}',0.03,2, NOW() - INTERVAL 90 MINUTE + INTERVAL 2 SECOND, NOW() - INTERVAL 90 MINUTE + INTERVAL 5 SECOND),

-- run_004: openclaw_session (2 steps)
('step_030','run_20260402_004','agent_call','intent_parse','OpenClawAgent','qwen-plus','completed','user_msg=查一下订单 ORD-88921 的物流','意图识别: order_tracking, entity: ORD-88921','{"total_tokens":120,"prompt_tokens":80,"completion_tokens":40}',0.008,0, NOW() - INTERVAL 1 HOUR, NOW() - INTERVAL 1 HOUR + INTERVAL 1 SECOND),
('step_031','run_20260402_004','tool_call','logistics_query','OpenClawAgent',NULL,'completed','order_id=ORD-88921','订单 ORD-88921 已发货，预计明天送达；快递: SF1234567890','{"total_tokens":200,"prompt_tokens":140,"completion_tokens":60}',0.012,0, NOW() - INTERVAL 1 HOUR + INTERVAL 1 SECOND, NOW() - INTERVAL 1 HOUR + INTERVAL 4 SECOND),

-- run_005: paused business_overview (3 steps, last one paused for HITL)
('step_040','run_20260402_005','service_call','data_preparation','BusinessOverviewWorkflow',NULL,'completed','sources=[orders, customers, fraud, reviews, inventory]','数据准备完成：935,261 行','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 4 HOUR, NOW() - INTERVAL 4 HOUR + INTERVAL 2 SECOND),
('step_041','run_20260402_005','service_call','fraud_scoring','BusinessOverviewWorkflow',NULL,'completed','batch mode','高风险交易 5 笔，需人工审核','{"total_tokens":0}',0.0,0, NOW() - INTERVAL 4 HOUR + INTERVAL 2 SECOND, NOW() - INTERVAL 4 HOUR + INTERVAL 5 SECOND),
('step_042','run_20260402_005','agent_call','hitl_gate','RiskReviewWorkflow',NULL,'paused','high_risk_count=5','等待人工审核：5 笔高风险交易需确认','{"total_tokens":1200}',0.08,0, NOW() - INTERVAL 4 HOUR + INTERVAL 5 SECOND, NULL)

ON DUPLICATE KEY UPDATE
  started_at = VALUES(started_at),
  ended_at   = VALUES(ended_at);
