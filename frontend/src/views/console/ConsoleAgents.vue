<template>
  <div class="cag">
    <div class="cag__toolbar">
      <div class="cag__tb-left">
        <h2 class="cag__title">智能体注册</h2>
        <span class="cag__derived">基于 Traces 与配置</span>
      </div>
      <V2Button variant="ghost" size="sm" :loading="loading" @click="load">刷新</V2Button>
    </div>

    <div class="cag__split" v-loading="loading">
      <!-- Left: agent cards -->
      <div class="cag__list">
        <div v-for="a in agents" :key="a.key" class="cag__card" :class="{ 'cag__card--active': sel?.key === a.key, 'cag__card--err': a.error_calls > 0 }" @click="sel = a">
          <div class="cag__card-top">
            <span class="cag__card-name">{{ a.label }}</span>
            <span class="cag__st" :class="'cag__st--' + a.healthClass">{{ a.healthLabel }}</span>
          </div>
          <div class="cag__card-desc">{{ a.description }}</div>
          <div class="cag__card-tools">
            <span v-for="t in a.tools" :key="t" class="cag__tool">{{ t }}</span>
          </div>
          <div class="cag__card-strip">
            <span><strong>{{ a.total_calls }}</strong> 调用</span>
            <span :class="a.error_calls > 0 ? 'cag__err-text' : ''"><strong>{{ a.error_calls }}</strong> 失败</span>
            <span><strong>{{ a.avg_latency_ms }}</strong>ms 均耗</span>
          </div>
        </div>
      </div>

      <!-- Right: detail -->
      <div class="cag__detail" v-if="sel">
        <div class="cag__dh">
          <div>
            <div class="cag__dh-name">{{ sel.label }}</div>
            <div class="cag__dh-desc">{{ sel.description }}</div>
          </div>
          <span class="cag__st" :class="'cag__st--' + sel.healthClass">{{ sel.healthLabel }}</span>
        </div>

        <!-- Status strip -->
        <div class="cag__runtime">
          <div class="cag__rc"><span class="cag__rc-k">总调用</span><span class="cag__rc-v">{{ sel.total_calls }}</span></div>
          <div class="cag__rc"><span class="cag__rc-k">成功</span><span class="cag__rc-v cag__rc-v--ok">{{ sel.success_calls }}</span></div>
          <div class="cag__rc"><span class="cag__rc-k">失败</span><span class="cag__rc-v" :class="sel.error_calls > 0 ? 'cag__rc-v--err' : ''">{{ sel.error_calls }}</span></div>
          <div class="cag__rc"><span class="cag__rc-k">平均耗时</span><span class="cag__rc-v">{{ sel.avg_latency_ms }}ms</span></div>
          <div class="cag__rc"><span class="cag__rc-k">失败率</span><span class="cag__rc-v" :class="sel.error_calls > 0 ? 'cag__rc-v--err' : ''">{{ sel.total_calls > 0 ? Math.round(sel.error_calls / sel.total_calls * 100) : 0 }}%</span></div>
        </div>

        <!-- Tools -->
        <div class="cag__sec">
          <div class="cag__sec-label">工具列表</div>
          <div class="cag__tools-grid">
            <span v-for="t in sel.tools" :key="t" class="cag__tool cag__tool--lg">{{ t }}</span>
          </div>
        </div>

        <!-- Workflows -->
        <div class="cag__sec" v-if="sel.workflows.length">
          <div class="cag__sec-label">参与的工作流</div>
          <div class="cag__wfs">
            <button v-for="wf in sel.workflows" :key="wf" class="cag__wf-chip" @click="viewTraces(wf)">{{ wf }} →</button>
          </div>
        </div>

        <!-- Recent errors -->
        <div class="cag__sec">
          <div class="cag__sec-label">最近错误 <span v-if="sel.recent_errors.length" class="cag__sec-count">{{ sel.recent_errors.length }}</span></div>
          <div v-if="sel.recent_errors.length" class="cag__errs">
            <div v-for="(err, i) in sel.recent_errors" :key="i" class="cag__err" @click="$router.push(`/console/traces/${err.run_id}`)">
              <span class="cag__err-dot" />
              <span class="cag__mono">{{ err.run_id?.slice(0, 10) }}</span>
              <span class="cag__err-msg">{{ err.error || '未知错误' }}</span>
            </div>
          </div>
          <div v-else class="cag__nil-ok">✓ 暂无错误记录</div>
        </div>
      </div>
      <div class="cag__detail cag__detail--empty" v-else><span class="cag__muted">← 选择一个 Agent</span></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/api/admin/index'
import V2Button from '@/components/v2/V2Button.vue'

const router = useRouter(), loading = ref(false), sel = ref(null)

const AGENT_META = {
  customer_agent:    { label: '客户分析 Agent',     description: 'RFM 分层 · KMeans 聚类 · XGBoost 流失预测 · BG-NBD CLV', tools: ['rfm_analysis', 'kmeans_cluster', 'churn_predict', 'clv_calc'] },
  forecast_agent:    { label: '销售预测 Agent',     description: 'SARIMA + HW-ETS + GRU + XGBoost → Stacking 融合预测', tools: ['sarima', 'hw_ets', 'gru_model', 'xgb_stacking'] },
  fraud_agent:       { label: '欺诈风控 Agent',     description: '规则引擎 + IsolationForest + LightGBM + AutoEncoder', tools: ['rule_engine', 'iso_forest', 'lgb_scorer', 'autoencoder'] },
  sentiment_agent:   { label: '舆情分析 Agent',     description: 'BERT-Chinese 情感分类 · LDA 主题建模 · TF-IDF + SVC', tools: ['bert_classifier', 'lda_topic', 'tfidf_svc'] },
  inventory_agent:   { label: '库存优化 Agent',     description: 'ABC-XYZ 分类 · EOQ 经济批量 · 安全库存计算', tools: ['abc_xyz', 'eoq_calc', 'safety_stock'] },
  openclaw_agent:    { label: 'OpenClaw 客服 Agent', description: '7×24 智能客服，意图识别 · FAQ 检索 · 工单创建 · 升级转人工', tools: ['faq_retriever', 'order_query', 'ticket_create', 'escalation'] },
  association_agent: { label: '关联分析 Agent',     description: 'Apriori + FP-Growth 关联规则挖掘与商品推荐', tools: ['apriori_engine', 'fpgrowth'] },
}

const STATUS_MAP = {
  ready:   { label: '就绪', cls: 'active' },
  unknown: { label: '未知', cls: 'idle' },
}

const agents = ref([])
function viewTraces(wf) { router.push({ path: '/console/traces', query: { workflow_name: wf } }) }

async function load() {
  loading.value = true
  try {
    const data = await adminApi.getAgentsOverview()
    const serverAgents = data?.agents ?? []
    const byName = {}
    for (const a of serverAgents) byName[a.name] = a

    agents.value = Object.entries(AGENT_META).map(([key, meta]) => {
      const s = byName[key] || {}
      const st = STATUS_MAP[s.status] || STATUS_MAP.unknown
      return {
        key,
        ...meta,
        status:         s.status || 'unknown',
        healthLabel:    st.label,
        healthClass:    st.cls,
        total_calls:    s.total_calls || 0,
        success_calls:  s.success_calls || 0,
        error_calls:    s.error_calls || 0,
        avg_latency_ms: s.avg_latency_ms || 0,
        workflows:      s.workflows || [],
        recent_errors:  s.recent_errors || [],
      }
    })
  } catch (e) {
    console.warn('[Agents]', e)
    console.warn('[Agents] load fallback')
    agents.value = Object.entries(AGENT_META).map(([key, meta]) => ({
      key, ...meta, status: 'unknown', healthLabel: '未知', healthClass: 'idle',
      total_calls: 0, success_calls: 0, error_calls: 0, avg_latency_ms: 0, workflows: [], recent_errors: [],
    }))
  }
  finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.cag__toolbar { display: flex; align-items: center; gap: var(--v2-space-3); padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); }
.cag__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); flex: 1; }
.cag__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.cag__derived { font-size: 9px; padding: 1px 6px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; font-weight: var(--v2-font-semibold); letter-spacing: .5px; }

.cag__split { display: grid; grid-template-columns: 1fr 1fr; gap: var(--v2-space-3); min-height: calc(100vh - 180px); }

.cag__list { display: flex; flex-direction: column; gap: var(--v2-space-2); overflow-y: auto; }
.cag__card { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-3); cursor: pointer; transition: all var(--v2-trans-fast); }
.cag__card:hover { border-color: var(--v2-brand-primary); }
.cag__card--active { border-color: var(--v2-brand-primary); background: var(--v2-brand-bg); }
.cag__card--err { border-left: 3px solid var(--v2-error); }
.cag__card--active.cag__card--err { border-left-color: var(--v2-brand-primary); }
.cag__card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
.cag__card-name { font-size: 13px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.cag__card-desc { font-size: 11px; color: var(--v2-text-3); margin-bottom: 6px; }
.cag__card-tools { display: flex; gap: 3px; flex-wrap: wrap; margin-bottom: 6px; }
.cag__tool { font-size: 9px; padding: 1px 5px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: 3px; }
.cag__tool--lg { font-size: 10px; padding: 2px 7px; }
.cag__card-strip { display: flex; gap: var(--v2-space-4); font-size: 10px; color: var(--v2-text-4); padding-top: 6px; border-top: 1px solid var(--v2-border-1); }
.cag__card-strip strong { color: var(--v2-text-1); font-weight: var(--v2-font-semibold); }

.cag__st { font-size: 10px; font-weight: var(--v2-font-medium); padding: 1px 5px; border-radius: 3px; }
.cag__st--active { background: var(--v2-success-bg); color: var(--v2-success-text); }
.cag__st--idle { background: var(--v2-bg-sunken); color: var(--v2-text-4); }

.cag__detail { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--v2-space-3); }
.cag__detail--empty { align-items: center; justify-content: center; }

.cag__dh { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: var(--v2-space-3); border-bottom: 1px solid var(--v2-border-2); }
.cag__dh-name { font-size: var(--v2-text-lg); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); }
.cag__dh-desc { font-size: 12px; color: var(--v2-text-3); margin-top: 2px; }

.cag__runtime { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
.cag__rc { padding: 6px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); text-align: center; }
.cag__rc-k { display: block; font-size: 9px; color: var(--v2-text-4); text-transform: uppercase; }
.cag__rc-v { font-size: 14px; font-weight: var(--v2-font-bold); color: var(--v2-text-1); font-variant-numeric: tabular-nums; }
.cag__rc-v--ok { color: var(--v2-success); } .cag__rc-v--err { color: var(--v2-error); }

.cag__sec { } .cag__sec-label { font-size: 10px; font-weight: var(--v2-font-semibold); color: var(--v2-text-4); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.cag__sec-count { font-size: 9px; padding: 0 4px; background: var(--v2-error-bg); color: var(--v2-error-text); border-radius: 3px; }

.cag__tools-grid { display: flex; gap: 4px; flex-wrap: wrap; }

.cag__wfs { display: flex; gap: 4px; flex-wrap: wrap; }
.cag__wf-chip { font-size: 10px; padding: 2px 8px; background: var(--v2-brand-bg); color: var(--v2-brand-primary); border: none; border-radius: 3px; cursor: pointer; font-weight: var(--v2-font-medium); } .cag__wf-chip:hover { background: var(--v2-brand-primary); color: #fff; }

.cag__errs { display: flex; flex-direction: column; gap: 3px; }
.cag__err { display: flex; align-items: center; gap: 6px; padding: 5px 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); cursor: pointer; font-size: 11px; transition: background var(--v2-trans-fast); }
.cag__err:hover { background: var(--v2-border-1); }
.cag__err-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--v2-error); flex-shrink: 0; }
.cag__err-msg { color: var(--v2-error); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cag__err-text { color: var(--v2-error); }

.cag__nil-ok { font-size: 11px; color: var(--v2-success); }
.cag__mono { font-family: var(--v2-font-mono); font-size: 10px; color: var(--v2-text-3); }
.cag__muted { font-size: 12px; color: var(--v2-text-4); }

@media (max-width: 1200px) { .cag__split { grid-template-columns: 1fr; } }
</style>
