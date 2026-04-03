SET NAMES utf8mb4;

ALTER TABLE fraud_records
  MODIFY risk_level VARCHAR(16) NOT NULL;

UPDATE fraud_records
SET risk_level = CASE
  WHEN risk_level IN ('低风险', 'ä½Žé£Žé™©') THEN '低风险'
  WHEN risk_level IN ('中风险', 'ä¸é£Žé™©') THEN '中风险'
  WHEN risk_level IN ('高风险', 'é«˜é£Žé™©') THEN '高风险'
  WHEN risk_score >= 0.8000 THEN '高风险'
  WHEN risk_score >= 0.4000 THEN '中风险'
  ELSE '低风险'
END;

ALTER TABLE fraud_records
  MODIFY risk_level ENUM('低风险','中风险','高风险') NOT NULL;
