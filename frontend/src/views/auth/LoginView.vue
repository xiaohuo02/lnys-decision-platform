<template>
  <div class="login-view">
    <div class="login-view__header">
      <h2>欢迎登录</h2>
      <p>首次使用？ <router-link to="/register" class="login-view__link">申请员工账号</router-link></p>
    </div>

    <form @submit.prevent="handleLogin" class="login-view__form">
      <div class="login-view__field">
        <label class="login-view__label">系统账号</label>
        <input
          v-model="form.username"
          type="text"
          class="login-view__input"
          placeholder="请输入账号"
          autocomplete="username"
        />
      </div>
      <div class="login-view__field">
        <label class="login-view__label">密码</label>
        <div class="login-view__input-wrap">
          <input
            v-model="form.password"
            :type="showPwd ? 'text' : 'password'"
            class="login-view__input"
            placeholder="请输入密码"
            autocomplete="current-password"
          />
          <button type="button" class="login-view__eye" @click="showPwd = !showPwd">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <p v-if="auth.error" class="login-view__error">{{ auth.error }}</p>

      <button type="submit" class="login-view__btn" :disabled="auth.loading">
        <template v-if="auth.loading">
          <svg class="login-view__spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
          处理中...
        </template>
        <template v-else>
          进入工作台
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </template>
      </button>
    </form>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/useAuthStore'

const router = useRouter()
const route  = useRoute()
const auth   = useAuthStore()

const form = reactive({ username: '', password: '' })
const showPwd = ref(false)

async function handleLogin() {
  if (!form.username.trim()) { auth.error = '请输入账号'; return }
  if (!form.password) { auth.error = '请输入密码'; return }
  auth.error = null
  try {
    await auth.login(form)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch {
    // 错误已由 store 设置
  }
}
</script>

<style scoped>
.login-view { width: 100%; }

.login-view__header { margin-bottom: 36px; }
.login-view__header h2 {
  font-size: 26px;
  font-weight: var(--v2-font-semibold);
  margin: 0 0 8px;
}
.login-view__header p {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  margin: 0;
}

.login-view__link {
  color: var(--v2-text-1);
  font-weight: var(--v2-font-semibold);
  text-decoration: none;
  border-bottom: 1px solid var(--v2-border-1);
  padding-bottom: 1px;
  transition: border-color 0.2s;
}
.login-view__link:hover {
  border-color: var(--v2-text-1);
}

.login-view__form { display: flex; flex-direction: column; }

.login-view__field {
  margin-bottom: 20px;
  position: relative;
}

.login-view__label {
  display: block;
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  margin-bottom: 8px;
  color: var(--v2-text-1);
}

.login-view__input {
  width: 100%;
  padding: 12px 14px;
  border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-input);
  font-size: var(--v2-text-md);
  color: var(--v2-text-1);
  font-family: var(--v2-font-sans);
  outline: none;
  transition: var(--v2-trans-fast);
  background: var(--v2-bg-card);
}
.login-view__input::placeholder { color: var(--v2-text-4); }
.login-view__input:hover { border-color: var(--v2-gray-400); }
.login-view__input:focus {
  border-color: var(--v2-gray-900);
  box-shadow: 0 0 0 1px var(--v2-gray-900);
}

.login-view__input-wrap { position: relative; }
.login-view__input-wrap .login-view__input { padding-right: 40px; }

.login-view__eye {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--v2-text-4);
  display: flex;
  padding: 0;
}
.login-view__eye:hover { color: var(--v2-text-1); }

.login-view__error {
  color: var(--v2-error);
  font-size: var(--v2-text-sm);
  margin: 0 0 12px;
}

.login-view__btn {
  width: 100%;
  padding: 14px;
  margin-top: 4px;
  background: var(--v2-gray-900);
  color: #fff;
  border: none;
  border-radius: var(--v2-radius-btn);
  font-size: var(--v2-text-md);
  font-weight: var(--v2-font-semibold);
  cursor: pointer;
  font-family: var(--v2-font-sans);
  transition: background 0.15s, transform 0.1s;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}
.login-view__btn:hover { background: var(--v2-gray-800); }
.login-view__btn:active { transform: scale(0.98); }
.login-view__btn:disabled { opacity: 0.7; cursor: not-allowed; }

@keyframes spin { 100% { transform: rotate(360deg); } }
.login-view__spin { animation: spin 1s linear infinite; }
</style>
