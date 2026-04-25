<template>
  <div class="auth-layout">
    <!-- 左侧品牌区 -->
    <div class="auth-layout__brand">
      <div class="auth-layout__brand-top">
        <div class="auth-layout__logo-icon">柠</div>
        <span>柠优生活数据中台</span>
      </div>

      <div class="auth-layout__brand-center">
        <h1>精准洞察。<br><span class="auth-layout__brand-muted">极简协同。</span></h1>
        <p>企业级大数据智能决策平台，专注于数据资产沉淀与 AI 辅助分析。为您屏蔽繁杂的噪音，直达最核心的业务信号与结论。</p>
        <div class="auth-layout__tags">
          <span class="auth-layout__tag">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            多维数据分析
          </span>
          <span class="auth-layout__tag">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
            AI 决策助手
          </span>
          <span class="auth-layout__tag">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            企业级安全
          </span>
          <span class="auth-layout__tag">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            全链路追踪
          </span>
        </div>
      </div>

      <div class="auth-layout__brand-bottom">
        <span class="auth-layout__status-dot"></span>
        系统版本 v5.0.0 · 内置 AI Copilot
      </div>
    </div>

    <!-- 右侧表单区（固定 480px） -->
    <div class="auth-layout__form-side">
      <router-view />
      <div class="auth-layout__footer">登录即同意《服务条款》与《隐私政策》</div>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.auth-layout {
  display: flex;
  height: calc(100vh / 1.2);
  zoom: 1.2;
  background: var(--v2-gray-100);
  font-family: var(--v2-font-sans);
  color: var(--v2-text-1);
}

/* ── 左侧品牌 ── */
.auth-layout__brand {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px 56px;
  position: relative;
  overflow: hidden;
}

.auth-layout__brand::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, var(--v2-gray-300) 0.8px, transparent 0.8px);
  background-size: 20px 20px;
  opacity: 0.5;
  mask-image: linear-gradient(to bottom right, black 30%, transparent 80%);
  -webkit-mask-image: linear-gradient(to bottom right, black 30%, transparent 80%);
  pointer-events: none;
}

.auth-layout__brand-top {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  z-index: 1;
}

.auth-layout__logo-icon {
  width: 28px;
  height: 28px;
  background: var(--v2-gray-900);
  color: #fff;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--v2-font-bold);
  font-size: var(--v2-text-sm);
}

.auth-layout__brand-center {
  z-index: 1;
}

.auth-layout__brand-center h1 {
  font-size: 42px;
  font-weight: var(--v2-font-bold);
  line-height: 1.35;
  letter-spacing: 1px;
  margin: 0 0 20px;
}

.auth-layout__brand-muted {
  color: var(--v2-text-3);
}

.auth-layout__brand-center p {
  font-size: var(--v2-text-md);
  color: var(--v2-text-3);
  line-height: 1.8;
  max-width: 420px;
  margin: 0;
}

.auth-layout__tags {
  margin-top: 36px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.auth-layout__tag {
  padding: 8px 16px;
  background: var(--v2-bg-card);
  border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-full);
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.auth-layout__tag svg {
  color: var(--v2-text-1);
}

.auth-layout__brand-bottom {
  z-index: 1;
  font-size: var(--v2-text-sm);
  color: var(--v2-text-4);
  display: flex;
  align-items: center;
  gap: 8px;
}

.auth-layout__status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--v2-success);
  display: block;
}

/* ── 右侧表单 ── */
.auth-layout__form-side {
  width: 480px;
  flex-shrink: 0;
  background: var(--v2-bg-card);
  border-left: var(--v2-border-width) solid var(--v2-border-1);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 60px 48px;
  overflow-y: auto;
}

.auth-layout__footer {
  margin-top: 32px;
  padding-top: 20px;
  border-top: var(--v2-border-width) solid var(--v2-border-1);
  text-align: center;
  font-size: 12px;
  color: var(--v2-text-4);
}

@media (max-width: 900px) {
  .auth-layout { flex-direction: column; height: auto; }
  .auth-layout__brand { padding: 32px; }
  .auth-layout__brand-center h1 { font-size: 28px; }
  .auth-layout__form-side {
    width: 100%;
    padding: 32px 24px;
    border-left: none;
    border-top: var(--v2-border-width) solid var(--v2-border-1);
  }
}
</style>
