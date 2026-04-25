<template>
  <div class="register-view">
    <div class="register-view__header">
      <h2>申请员工账号</h2>
      <p>已有账号？ <router-link to="/login" class="register-view__link">返回登录</router-link></p>
    </div>

    <form @submit.prevent="handleRegister" class="register-view__form">
      <div class="register-view__field">
        <label class="register-view__label">真实姓名</label>
        <input
          v-model="form.real_name"
          type="text"
          class="register-view__input"
          placeholder="请输入真实姓名"
          @input="updatePreview"
        />
        <div class="register-view__hint">
          自动生成账号：<span class="register-view__hint-val">{{ accountPreview || '—' }}</span>
        </div>
      </div>

      <div class="register-view__field">
        <label class="register-view__label">设置密码</label>
        <div class="register-view__input-wrap">
          <input
            v-model="form.password"
            :type="showPwd ? 'text' : 'password'"
            class="register-view__input"
            placeholder="请设置登录密码（至少 6 位）"
          />
          <button type="button" class="register-view__eye" @click="showPwd = !showPwd">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>

      <div class="register-view__field">
        <label class="register-view__label">企业授权码</label>
        <input
          v-model="form.auth_code"
          type="text"
          class="register-view__input"
          placeholder="请输入管理员提供的授权码"
        />
      </div>

      <div class="register-view__notice">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <div>注册后默认为 <b>员工角色</b>，仅可进入业务空间查看数据。管理员授权后开放操作权限。</div>
      </div>

      <p v-if="auth.error" class="register-view__error">{{ auth.error }}</p>
      <p v-if="successMsg" class="register-view__success">{{ successMsg }}</p>

      <button type="submit" class="register-view__btn" :disabled="auth.loading">
        <template v-if="auth.loading">
          <svg class="register-view__spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
          处理中...
        </template>
        <template v-else>提交注册申请</template>
      </button>
    </form>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/useAuthStore'

const router = useRouter()
const auth   = useAuthStore()

const form = reactive({ real_name: '', password: '', auth_code: '' })
const showPwd = ref(false)
const accountPreview = ref('')
const successMsg = ref('')

const PINYIN_MAP = {
  '赵':'zhao','钱':'qian','孙':'sun','李':'li','周':'zhou','吴':'wu','郑':'zheng','王':'wang',
  '冯':'feng','陈':'chen','褚':'chu','卫':'wei','蒋':'jiang','沈':'shen','韩':'han','杨':'yang',
  '朱':'zhu','秦':'qin','尤':'you','许':'xu','何':'he','吕':'lv','施':'shi','张':'zhang',
  '孔':'kong','曹':'cao','严':'yan','华':'hua','金':'jin','魏':'wei','陶':'tao','姜':'jiang',
  '戚':'qi','谢':'xie','邹':'zou','喻':'yu','柏':'bai','章':'zhang','苏':'su','潘':'pan',
  '葛':'ge','范':'fan','彭':'peng','鲁':'lu','韦':'wei','马':'ma','苗':'miao','方':'fang',
  '任':'ren','袁':'yuan','柳':'liu','邓':'deng','史':'shi','唐':'tang','薛':'xue','雷':'lei',
  '贺':'he','倪':'ni','罗':'luo','郝':'hao','安':'an','常':'chang','于':'yu','傅':'fu',
  '齐':'qi','康':'kang','余':'yu','元':'yuan','顾':'gu','孟':'meng','黄':'huang','穆':'mu',
  '萧':'xiao','尹':'yin','姚':'yao','邵':'shao','汪':'wang','祁':'qi','米':'mi','贝':'bei',
  '明':'ming','成':'cheng','戴':'dai','宋':'song','庞':'pang','熊':'xiong','纪':'ji','舒':'shu',
  '屈':'qu','项':'xiang','祝':'zhu','董':'dong','梁':'liang','杜':'du','阮':'ruan','蓝':'lan',
  '闵':'min','季':'ji','贾':'jia','路':'lu','童':'tong','颜':'yan','郭':'guo','梅':'mei',
  '盛':'sheng','林':'lin','钟':'zhong','徐':'xu','骆':'luo','高':'gao','夏':'xia','蔡':'cai',
  '田':'tian','胡':'hu','凌':'ling','霍':'huo','万':'wan','柯':'ke','卢':'lu','莫':'mo',
  '白':'bai','房':'fang','龚':'gong','程':'cheng','邢':'xing','裴':'pei','陆':'lu','荣':'rong',
  '段':'duan','侯':'hou','武':'wu','刘':'liu','景':'jing','詹':'zhan','龙':'long','叶':'ye',
  '洪':'hong','丁':'ding','包':'bao','崔':'cui','石':'shi','江':'jiang',
  '伟':'wei','芳':'fang','娜':'na','敏':'min','静':'jing','丽':'li','强':'qiang','磊':'lei',
  '军':'jun','洋':'yang','勇':'yong','艳':'yan','杰':'jie','涛':'tao','春':'chun','飞':'fei',
  '超':'chao','浩':'hao','亮':'liang','平':'ping','辉':'hui','刚':'gang','英':'ying',
  '红':'hong','文':'wen','建':'jian','国':'guo','志':'zhi','天':'tian','新':'xin','海':'hai',
  '波':'bo','宇':'yu','鑫':'xin','博':'bo','睿':'rui','晨':'chen','旭':'xu','俊':'jun',
  '子':'zi','佳':'jia','思':'si','雨':'yu','欣':'xin','怡':'yi','琳':'lin','瑶':'yao',
  '洁':'jie','颖':'ying','婷':'ting','雪':'xue','慧':'hui','梦':'meng','涵':'han','紫':'zi',
  '妍':'yan','月':'yue','星':'xing','阳':'yang','德':'de','正':'zheng','庆':'qing','瑞':'rui',
  '峰':'feng','昊':'hao','翔':'xiang','鹏':'peng','小':'xiao','大':'da','中':'zhong',
  '长':'chang','兴':'xing','家':'jia','永':'yong','美':'mei','玉':'yu','凤':'feng',
  '兰':'lan','燕':'yan','秀':'xiu','珍':'zhen','玲':'ling','冰':'bing','雅':'ya',
  '萍':'ping','莉':'li','彬':'bin','松':'song','岩':'yan','光':'guang','立':'li',
  '东':'dong','南':'nan','西':'xi','北':'bei','清':'qing','毅':'yi','恒':'heng',
  '忠':'zhong','义':'yi','信':'xin','仁':'ren','礼':'li','智':'zhi','勤':'qin',
  '和':'he','谦':'qian','祥':'xiang','福':'fu','康':'kang','宁':'ning','乐':'le',
  '成':'cheng','功':'gong','达':'da','发':'fa','富':'fu','贵':'gui','荣':'rong','华':'hua',
}

function updatePreview() {
  const name = form.real_name.trim()
  if (!name) { accountPreview.value = ''; return }
  let result = ''
  for (const ch of name) {
    if (PINYIN_MAP[ch]) result += PINYIN_MAP[ch]
    else if (/[a-zA-Z]/.test(ch)) result += ch.toLowerCase()
  }
  accountPreview.value = result || ''
}

async function handleRegister() {
  if (!form.real_name.trim()) { auth.error = '请输入真实姓名'; return }
  if (form.password.length < 6) { auth.error = '密码长度不能少于 6 位'; return }
  if (!form.auth_code.trim()) { auth.error = '请输入企业授权码'; return }
  auth.error = null
  successMsg.value = ''
  try {
    const res = await auth.register(form)
    successMsg.value = `${res.message}，您的账号为：${res.username}`
    ElMessage.success(res.message || '注册成功')
    setTimeout(() => router.push('/login'), 2000)
  } catch {
    // 错误已由 store 设置
  }
}
</script>

<style scoped>
.register-view { width: 100%; }

.register-view__header { margin-bottom: 36px; }
.register-view__header h2 {
  font-size: 26px;
  font-weight: var(--v2-font-semibold);
  margin: 0 0 8px;
}
.register-view__header p {
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  margin: 0;
}

.register-view__link {
  color: var(--v2-text-1);
  font-weight: var(--v2-font-semibold);
  text-decoration: none;
  border-bottom: 1px solid var(--v2-border-1);
  padding-bottom: 1px;
  transition: border-color 0.2s;
}
.register-view__link:hover { border-color: var(--v2-text-1); }

.register-view__form { display: flex; flex-direction: column; }

.register-view__field {
  margin-bottom: 20px;
  position: relative;
}

.register-view__label {
  display: block;
  font-size: var(--v2-text-sm);
  font-weight: var(--v2-font-medium);
  margin-bottom: 8px;
  color: var(--v2-text-1);
}

.register-view__input {
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
.register-view__input::placeholder { color: var(--v2-text-4); }
.register-view__input:hover { border-color: var(--v2-gray-400); }
.register-view__input:focus {
  border-color: var(--v2-gray-900);
  box-shadow: 0 0 0 1px var(--v2-gray-900);
}

.register-view__input-wrap { position: relative; }
.register-view__input-wrap .register-view__input { padding-right: 40px; }

.register-view__eye {
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
.register-view__eye:hover { color: var(--v2-text-1); }

.register-view__hint {
  margin-top: 8px;
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
}
.register-view__hint-val {
  color: var(--v2-text-1);
  font-weight: var(--v2-font-semibold);
  font-family: var(--v2-font-mono);
}

.register-view__notice {
  margin-top: 4px;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: var(--v2-gray-50);
  border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-input);
  font-size: var(--v2-text-sm);
  color: var(--v2-text-3);
  line-height: 1.7;
  display: flex;
  gap: 10px;
}
.register-view__notice svg {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--v2-text-1);
}

.register-view__error {
  color: var(--v2-error);
  font-size: var(--v2-text-sm);
  margin: 0 0 12px;
}
.register-view__success {
  color: var(--v2-success);
  font-size: var(--v2-text-sm);
  margin: 0 0 12px;
}

.register-view__btn {
  width: 100%;
  padding: 14px;
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
.register-view__btn:hover { background: var(--v2-gray-800); }
.register-view__btn:active { transform: scale(0.98); }
.register-view__btn:disabled { opacity: 0.7; cursor: not-allowed; }

@keyframes spin { 100% { transform: rotate(360deg); } }
.register-view__spin { animation: spin 1s linear infinite; }
</style>
