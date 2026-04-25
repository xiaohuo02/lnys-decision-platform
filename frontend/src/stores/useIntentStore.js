/**
 * useIntentStore — 跨页 Intent 传递（C-α）
 *
 * 解决"模块之间没联系"：
 *   Dashboard 点击"去审核" → dispatch('review_high_risk', {...}) + router.push('/fraud')
 *   FraudDetection onMounted → consume('review_high_risk') → 切到待审 Tab + 预筛数据
 *
 * 约定：
 *   - 同一时刻只保留最近一次 dispatch（单槽），简单避免冲突
 *   - dispatch 后由目标页 consume（读取 + 清空），防止重复触发
 *   - peek 仅读取不清空（用于调试或预览）
 *
 * Intent 类型（约定命名空间）：
 *   - 'review_high_risk'      fraud  → 高风险交易审核
 *   - 'view_churn_customers'  customer → 流失风险客户
 *   - 'replenish_sku'         inventory → 补货建议
 *   - 'analyze_negative'      sentiment/analyze → 负面舆情分析
 *   - 'analyze_kpi'           analyze → 针对某个 KPI 做归因
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useIntentStore = defineStore('intent', () => {
  // { type, payload, origin, ts } | null
  const pending = ref(null)

  /**
   * 发起一个 intent。
   * @param {string} type     — intent 类型（命名空间约定见上）
   * @param {object} payload  — 业务数据（如 { threshold: 0.7, count: 14 }）
   * @param {string} origin   — 来源页面标识（如 'dashboard'），便于目标页显示"从 X 跳转而来"
   */
  function dispatch(type, payload = {}, origin = '') {
    if (!type) return
    pending.value = { type, payload, origin, ts: Date.now() }
  }

  /**
   * 消费 intent：读取 + 清空。仅当 pending 的 type 匹配时才消费。
   * 目标页通常在 onMounted / onActivated 时调用。
   * @returns {{type, payload, origin, ts} | null}
   */
  function consume(type) {
    if (pending.value?.type === type) {
      const p = pending.value
      pending.value = null
      return p
    }
    return null
  }

  /**
   * 只读当前 intent（不清空）。
   */
  function peek(type) {
    if (type === undefined) return pending.value
    return pending.value?.type === type ? pending.value : null
  }

  /**
   * 强制清空（用户手动取消上下文时用）。
   */
  function clear() {
    pending.value = null
  }

  return { pending, dispatch, consume, peek, clear }
})
