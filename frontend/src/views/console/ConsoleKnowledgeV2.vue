<template>
  <div class="kb2">
    <!-- Toolbar -->
    <div class="kb2__toolbar">
      <div class="kb2__tb-left">
        <h2 class="kb2__title">知识库中台</h2>
        <span class="kb2__count">{{ libraries.length }} 个知识库</span>
      </div>
      <div class="kb2__tb-actions">
        <el-input v-model="searchQuery" placeholder="全局检索" clearable size="small" style="width:220px" @keyup.enter="doSearch">
          <template #append><el-button @click="doSearch" :icon="Search" /></template>
        </el-input>
        <el-button type="primary" size="small" @click="showCreateLib = true">+ 新建知识库</el-button>
      </div>
    </div>

    <!-- Tab nav -->
    <div class="kb2__tabs">
      <div class="kb2__tab" :class="{ 'kb2__tab--active': tab === 'libs' }" @click="tab = 'libs'">知识库管理</div>
      <div class="kb2__tab" :class="{ 'kb2__tab--active': tab === 'search' }" @click="tab = 'search'">统一检索</div>
      <div class="kb2__tab" :class="{ 'kb2__tab--active': tab === 'stats' }" @click="tab = 'stats'; loadStats()">统计概览</div>
      <div class="kb2__tab" :class="{ 'kb2__tab--active': tab === 'feedback' }" @click="tab = 'feedback'">用户反馈</div>
    </div>

    <!-- Tab: Libraries -->
    <div v-if="tab === 'libs'" class="kb2__panel">
      <div class="kb2__grid">
        <div v-for="lib in libraries" :key="lib.kb_id" class="kb2__card" @click="openLibrary(lib)">
          <div class="kb2__card-head">
            <component :is="libIcon(lib.domain)" class="kb2__card-icon" :size="18" :stroke-width="1.8" />
            <span class="kb2__card-name">{{ lib.display_name }}</span>
            <span class="kb2__card-health" :class="'kb2__card-health--' + libHealth(lib).key" :title="lib.is_active === false ? '该库已禁用' : ''">{{ libHealth(lib).label }}</span>
          </div>
          <div class="kb2__card-desc">{{ lib.description || '暂无描述' }}</div>
          <div class="kb2__card-foot">
            <span class="kb2__domain-chip">{{ domainLabel(lib.domain) }}</span>
            <span>{{ lib.doc_count ?? 0 }} 文档</span>
            <span>{{ lib.chunk_count ?? 0 }} 分块</span>
            <span class="kb2__card-time" v-if="lib.updated_at" :title="lib.updated_at">更新 {{ fmtRelTime(lib.updated_at) }}</span>
          </div>
          <div class="kb2__card-actions">
            <el-button size="small" type="danger" text @click.stop="doDeleteLib(lib)">删除</el-button>
          </div>
        </div>
      </div>

      <!-- Document panel (when a library is selected) -->
      <div v-if="currentLib" class="kb2__docs">
        <div class="kb2__docs-head">
          <h3>{{ currentLib.display_name }}  文档列表</h3>
          <el-button size="small" type="primary" @click="showCreateDoc = true">+ 添加文档</el-button>
          <el-button size="small" @click="currentLib = null">返回</el-button>
        </div>
        <el-table :data="documents" size="small" stripe>
          <el-table-column prop="title" label="标题" min-width="200">
            <template #default="{ row }">
              <el-link type="primary" :underline="false" @click.stop="openDocDetail(row)">{{ row.title }}</el-link>
            </template>
          </el-table-column>
          <el-table-column prop="source_type" label="来源" width="100" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <span class="kb2__st" :class="'kb2__st--' + row.status">{{ statusLabel(row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="chunk_count" label="分块数" width="80" />
          <el-table-column prop="quality_score" label="质量分" width="80">
            <template #default="{ row }">{{ row.quality_score ? row.quality_score.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="150" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" type="danger" text @click="doDeleteDoc(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- Tab: Search -->
    <div v-if="tab === 'search'" class="kb2__panel">
      <div class="kb2__search-bar">
        <el-input v-model="searchQuery" placeholder="输入检索内容" size="default" @keyup.enter="doSearch" />
        <el-select v-model="searchKbIds" multiple collapse-tags collapse-tags-tooltip placeholder="全部知识库" size="default" style="width:200px" clearable>
          <el-option v-for="lib in libraries" :key="lib.kb_id" :label="lib.display_name" :value="lib.kb_id" />
        </el-select>
        <el-select v-model="searchMode" size="default" style="width:120px">
          <el-option label="混合检索" value="hybrid" />
          <el-option label="向量检索" value="vector" />
          <el-option label="关键词" value="keyword" />
        </el-select>
        <el-button type="primary" @click="doSearch" :loading="searching">检索</el-button>
      </div>

      <!-- §4.3 #6 空搜索引导：未发起检索时显示热门 query chip -->
      <div v-if="!searching && !searchDone && !searchResults.length" class="kb2__chips">
        <span class="kb2__chips-label">试试搜：</span>
        <button v-for="q in SUGGESTED_QUERIES" :key="q" class="kb2__chip" @click="useSuggested(q)">{{ q }}</button>
      </div>

      <!-- §4.3 #3/#4 Search summary bar：置信度按 score 重判，降级合并为 inline badge -->
      <div v-if="searchDone && searchMeta" class="kb2__search-summary">
        <div class="kb2__summary-left">
          <span class="kb2__conf-badge" :class="'kb2__conf--' + confLevel(searchMeta.confidence_score)">
            {{ CONFIDENCE_LABEL[confLevel(searchMeta.confidence_score)] || searchMeta.confidence }}
          </span>
          <span class="kb2__conf-score">{{ (searchMeta.confidence_score * 100).toFixed(1) }}%</span>
          <span v-if="searchMeta.ambiguous" class="kb2__conf-ambiguous">⚠ 结果相近</span>
          <span v-if="searchMeta.reranked" class="kb2__rerank-tag">已重排</span>
          <el-tooltip v-if="searchMeta.degraded" effect="dark" :content="'检索降级原因：' + (searchMeta.degraded_reason || '未知')" placement="top">
            <span class="kb2__degraded-badge">⚠ 已降级</span>
          </el-tooltip>
        </div>
        <div class="kb2__summary-right">
          <span class="kb2__suggestion">{{ SUGGESTION_LABEL[searchMeta.suggestion] || searchMeta.suggestion }}</span>
          <span class="kb2__search-mode-tag">{{ searchMeta.search_mode }}</span>
          <span class="kb2__search-elapsed">{{ searchMeta.elapsed_ms }}ms</span>
        </div>
      </div>

      <!-- Loading skeleton -->
      <div v-if="searching" class="kb2__search-loading">
        <el-skeleton :rows="3" animated />
        <div class="kb2__search-loading-tip">正在检索，请稍候…</div>
      </div>

      <div v-else-if="searchResults.length" class="kb2__results">
        <!-- §4.3 #5：hit 可点击进入文档详情 dialog -->
        <div
          v-for="(hit, i) in searchResults"
          :key="i"
          class="kb2__hit"
          :class="{ 'kb2__hit--clickable': !!hit.document_id }"
          :title="hit.document_id ? '点击查看文档详情' : ''"
          @click="hit.document_id && openHitDoc(hit)"
        >
          <div class="kb2__hit-head">
            <span class="kb2__hit-rank">#{{ i + 1 }}</span>
            <span class="kb2__hit-score">{{ (hit.score * 100).toFixed(1) }}%</span>
            <span v-if="hit.rerank_score != null" class="kb2__hit-rerank">rerank {{ (hit.rerank_score * 100).toFixed(1) }}%</span>
            <span class="kb2__hit-mode">{{ hit.search_mode }}</span>
          </div>
          <div class="kb2__hit-content">{{ hit.content }}</div>
          <div class="kb2__hit-meta">
            <span v-if="hit.title">{{ hit.title }}</span>
            <span v-if="hit.kb_name">{{ hit.kb_name }}</span>
          </div>
        </div>
      </div>
      <div v-else-if="searchDone" class="kb2__nil">未找到匹配结果</div>
    </div>

    <!-- Tab: Feedback (§3.4 admin) -->
    <div v-if="tab === 'feedback'" class="kb2__panel">
      <KbFeedbackPanel />
    </div>

    <!-- Tab: Stats -->
    <div v-if="tab === 'stats'" class="kb2__panel">
      <div class="kb2__stats-grid">
        <div class="kb2__stat-card"><div class="kb2__stat-num">{{ stats.total_libraries ?? 0 }}</div><div class="kb2__stat-label">知识库</div></div>
        <div class="kb2__stat-card"><div class="kb2__stat-num">{{ stats.total_documents ?? 0 }}</div><div class="kb2__stat-label">文档</div></div>
        <div class="kb2__stat-card"><div class="kb2__stat-num">{{ stats.total_chunks ?? 0 }}</div><div class="kb2__stat-label">分块</div></div>
      </div>
    </div>

    <!-- Dialog: Create Library -->
    <el-dialog v-model="showCreateLib" title="新建知识库" width="500px">
      <el-form :model="libForm" label-width="100px" size="small">
        <el-form-item label="标识名"><el-input v-model="libForm.name" placeholder="如 product_faq" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="libForm.display_name" /></el-form-item>
        <el-form-item label="业务域">
          <el-select v-model="libForm.domain" style="width:100%">
            <el-option label="企业" value="enterprise" /><el-option label="舆情" value="sentiment" /><el-option label="运维" value="ops" /><el-option label="通用" value="general" />
          </el-select>
        </el-form-item>
        <el-form-item label="分块策略">
          <el-select v-model="libForm.chunk_strategy" style="width:100%">
            <el-option label="递归语义分块" value="recursive" /><el-option label="固定长度分块" value="fixed" /><el-option label="不分块" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="libForm.description" type="textarea" rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showCreateLib = false">取消</el-button><el-button type="primary" @click="doCreateLib" :loading="saving">创建</el-button></template>
    </el-dialog>

    <!-- Dialog: Document Detail -->
    <el-dialog v-model="showDocDetail" title="文档详情" width="720px" top="5vh">
      <template v-if="docDetail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="标题" :span="2">{{ docDetail.title }}</el-descriptions-item>
          <el-descriptions-item label="状态"><span class="kb2__st" :class="'kb2__st--' + docDetail.status">{{ statusLabel(docDetail.status) }}</span></el-descriptions-item>
          <el-descriptions-item label="版本">v{{ docDetail.version ?? 1 }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ docDetail.source_type }}</el-descriptions-item>
          <el-descriptions-item label="质量分">{{ docDetail.quality_score ? docDetail.quality_score.toFixed(2) : '-' }}</el-descriptions-item>
          <el-descriptions-item label="分块数">{{ docDetail.chunk_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ docDetail.created_at }}</el-descriptions-item>
        </el-descriptions>

        <div class="kb2__detail-tabs">
          <div class="kb2__detail-tab" :class="{ 'kb2__detail-tab--active': detailTab === 'content' }" @click="detailTab = 'content'">内容</div>
          <div class="kb2__detail-tab" :class="{ 'kb2__detail-tab--active': detailTab === 'chunks' }" @click="detailTab = 'chunks'">分块 ({{ docChunks.length }})</div>
          <div class="kb2__detail-tab" :class="{ 'kb2__detail-tab--active': detailTab === 'versions' }" @click="detailTab = 'versions'; loadVersions()">版本历史</div>
          <div style="flex:1"></div>
          <el-button size="small" type="warning" text @click="doReprocess" :loading="reprocessing">重新处理</el-button>
        </div>

        <!-- Tab: Content -->
        <div v-if="detailTab === 'content'">
          <el-divider content-position="left">清洗后内容</el-divider>
          <div class="kb2__doc-content">{{ docDetail.content_clean || '（无内容）' }}</div>
          <el-divider content-position="left">原始内容</el-divider>
          <div class="kb2__doc-content kb2__doc-content--raw">{{ docDetail.content_raw || '（无内容）' }}</div>
          <template v-if="docDetail.error_msg">
            <el-divider content-position="left">错误信息</el-divider>
            <el-alert :title="docDetail.error_msg" type="error" show-icon :closable="false" />
          </template>
        </div>

        <!-- Tab: Chunks（§4.3 #7：默认折叠 2 行，点击"展开"） -->
        <div v-if="detailTab === 'chunks'">
          <div v-if="docChunks.length" class="kb2__chunks-list">
            <div v-for="(chunk, ci) in docChunks" :key="chunk.chunk_id" class="kb2__chunk-item">
              <div class="kb2__chunk-head">
                <span class="kb2__chunk-idx">#{{ ci + 1 }}</span>
                <span class="kb2__chunk-type">{{ chunk.chunk_type }}</span>
                <span v-if="chunk.token_count" class="kb2__chunk-tokens">{{ chunk.token_count }} tokens</span>
                <span class="kb2__chunk-embed" :class="'kb2__st--' + chunk.embedding_status">{{ statusLabel(chunk.embedding_status) }}</span>
                <span class="kb2__chunk-toggle" @click="toggleChunk(chunk.chunk_id)">{{ isChunkExpanded(chunk.chunk_id) ? '收起' : '展开' }}</span>
              </div>
              <div class="kb2__chunk-text" :class="{ 'kb2__chunk-text--collapsed': !isChunkExpanded(chunk.chunk_id) }">{{ chunk.content }}</div>
            </div>
          </div>
          <div v-else class="kb2__nil">暂无分块数据</div>
        </div>

        <!-- Tab: Versions -->
        <div v-if="detailTab === 'versions'">
          <div v-if="docVersions.length" class="kb2__ver-list">
            <div v-for="ver in docVersions" :key="ver.version_id" class="kb2__ver-item">
              <div class="kb2__ver-head">
                <span class="kb2__ver-tag">v{{ ver.version }}</span>
                <span class="kb2__ver-time">{{ ver.created_at }}</span>
                <span class="kb2__ver-meta">{{ ver.chunk_count }} 分块</span>
                <span v-if="ver.quality_score" class="kb2__ver-meta">质量 {{ ver.quality_score.toFixed(2) }}</span>
                <span class="kb2__ver-by">{{ ver.created_by }}</span>
                <el-button v-if="ver.version !== docDetail.version" size="small" type="primary" text @click="doRollback(ver.version)" :loading="rollingBack">回退到此版本</el-button>
              </div>
            </div>
          </div>
          <div v-else class="kb2__nil">暂无历史版本（文档重新处理或回退后会自动生成版本快照）</div>
        </div>
      </template>
    </el-dialog>

    <!-- Dialog: Create Document -->
    <el-dialog v-model="showCreateDoc" title="添加文档" width="560px">
      <el-form :model="docForm" label-width="80px" size="small">
        <el-form-item label="标题"><el-input v-model="docForm.title" /></el-form-item>
        <el-form-item label="分组"><el-input v-model="docForm.group_name" placeholder="如 refund, shipping" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="docForm.content" type="textarea" rows="6" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showCreateDoc = false">取消</el-button><el-button type="primary" @click="doCreateDoc" :loading="saving">提交</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Building2, MessageCircle, Settings, BookOpen } from 'lucide-vue-next'
import { knowledgeV2Api } from '@/api/admin/knowledgeV2'
import KbFeedbackPanel from '@/components/console/KbFeedbackPanel.vue'

const tab = ref('libs')
const libraries = ref([])
const currentLib = ref(null)
const documents = ref([])
const searchQuery = ref('')
const searchMode = ref('hybrid')
const searchKbIds = ref([])
const searchResults = ref([])
const searchMeta = ref(null)
const searchDone = ref(false)
const searching = ref(false)
const stats = ref({})
const saving = ref(false)

const showCreateLib = ref(false)
const showCreateDoc = ref(false)
const showDocDetail = ref(false)
const docDetail = ref(null)
const docChunks = ref([])
const docVersions = ref([])
const detailTab = ref('content')
const rollingBack = ref(false)
const reprocessing = ref(false)
const libForm = ref({ name: '', display_name: '', description: '', domain: 'enterprise', chunk_strategy: 'recursive' })
const docForm = ref({ title: '', content: '', group_name: '' })

const STATUS_MAP = { pending: '待处理', processing: '处理中', ready: '就绪', failed: '失败', disabled: '已禁用', done: '完成' }
const DOMAIN_MAP = { enterprise: '企业', sentiment: '舆情', ops: '运维', general: '通用' }
// §4.3 #1：按 domain 固定 lucide 图标，避免不同系统 emoji fallback 差异
const DOMAIN_ICON = { enterprise: Building2, sentiment: MessageCircle, ops: Settings, general: BookOpen }
function statusLabel(s) { return STATUS_MAP[s] || s }
function domainLabel(d) { return DOMAIN_MAP[d] || d }
function libIcon(d) { return DOMAIN_ICON[d] || BookOpen }

const CONFIDENCE_LABEL = { high: '高置信', medium: '中置信', low: '低置信', none: '无结果', ambiguous: '结果歧义' }
const SUGGESTION_LABEL = { direct_answer: '可直接回答', show_candidates: '建议展示候选', fallback_faq: '建议走规则FAQ', transfer_human: '建议转人工', disambiguate: '建议澄清需求' }

// §4.3 #6：空搜索引导 chip。在接§3.3 Router 后可接入热门 query
const SUGGESTED_QUERIES = ['退款多久到账', '会员权益', '订单取消规则', '物流查询', '发票开具', '售后申请']

// §4.3 #3：置信度颜色按 score 实际值重判，不依赖后端 confidence 标签
function confLevel(score) {
  const s = Number(score || 0)
  if (s >= 0.75) return 'high'
  if (s >= 0.50) return 'medium'
  if (s >  0)    return 'low'
  return 'none'
}

// §4.3 #8：KB 卡健康 badge（限于当前后端字段推导，'热度' 需 §5 可观测性补字段后一起上）
function libHealth(lib) {
  if (lib?.is_active === false) return { key: 'disabled', label: '已禁用' }
  if (!lib?.chunk_count)        return { key: 'empty',    label: '未入库' }
  return { key: 'ok', label: '正常' }
}

function fmtRelTime(v) {
  if (!v) return ''
  const d = new Date(v); if (isNaN(d)) return ''
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  const mon = Math.floor(day / 30)
  if (mon < 12) return `${mon} 个月前`
  return `${Math.floor(mon / 12)} 年前`
}

// §4.3 #7：chunk 默认折叠，点击展开
const expandedChunks = ref(new Set())
function toggleChunk(id) {
  const set = new Set(expandedChunks.value)
  set.has(id) ? set.delete(id) : set.add(id)
  expandedChunks.value = set
}
function isChunkExpanded(id) { return expandedChunks.value.has(id) }

async function loadLibraries() {
  try {
    const r = await knowledgeV2Api.getLibraries()
    libraries.value = r?.items ?? (Array.isArray(r) ? r : [])
  } catch { libraries.value = [] }
}

async function openLibrary(lib) {
  currentLib.value = lib
  try {
    const r = await knowledgeV2Api.getDocuments(lib.kb_id, { limit: 100 })
    documents.value = r?.items ?? (Array.isArray(r) ? r : [])
  } catch { documents.value = [] }
}

async function doCreateLib() {
  saving.value = true
  try {
    await knowledgeV2Api.createLibrary(libForm.value)
    ElMessage.success('知识库创建成功')
    showCreateLib.value = false
    libForm.value = { name: '', display_name: '', description: '', domain: 'enterprise', chunk_strategy: 'recursive' }
    loadLibraries()
  } catch { ElMessage.error('创建失败') } finally { saving.value = false }
}

async function doDeleteLib(lib) {
  await ElMessageBox.confirm(`确定删除知识库「${lib.display_name}」？此操作不可恢复。`, '确认', { type: 'warning' })
  try {
    await knowledgeV2Api.deleteLibrary(lib.kb_id)
    ElMessage.success('已删除')
    if (currentLib.value?.kb_id === lib.kb_id) currentLib.value = null
    loadLibraries()
  } catch { ElMessage.error('删除失败') }
}

async function doCreateDoc() {
  if (!currentLib.value) return
  saving.value = true
  try {
    await knowledgeV2Api.createDocument(currentLib.value.kb_id, {
      title: docForm.value.title,
      content: docForm.value.content,
      source_type: 'faq_manual',
      group_name: docForm.value.group_name,
    })
    ElMessage.success('文档已提交处理')
    showCreateDoc.value = false
    docForm.value = { title: '', content: '', group_name: '' }
    setTimeout(() => openLibrary(currentLib.value), 1500)
  } catch { ElMessage.error('提交失败') } finally { saving.value = false }
}

async function openDocDetail(doc) {
  docDetail.value = null
  docChunks.value = []
  docVersions.value = []
  detailTab.value = 'content'
  showDocDetail.value = true
  try {
    const detail = await knowledgeV2Api.getDocument(doc.document_id)
    docDetail.value = detail
  } catch { docDetail.value = doc }
  try {
    const r = await knowledgeV2Api.getChunks(doc.document_id)
    docChunks.value = r?.items ?? (Array.isArray(r) ? r : [])
  } catch { docChunks.value = [] }
}

async function loadVersions() {
  if (!docDetail.value) return
  try {
    const r = await knowledgeV2Api.getVersions(docDetail.value.document_id)
    docVersions.value = r?.items ?? (Array.isArray(r) ? r : [])
  } catch { docVersions.value = [] }
}

async function doRollback(targetVersion) {
  if (!docDetail.value) return
  await ElMessageBox.confirm(`确定回退到 v${targetVersion}？当前版本将自动快照保存。`, '确认回退', { type: 'warning' })
  rollingBack.value = true
  try {
    await knowledgeV2Api.rollback(docDetail.value.document_id, { target_version: targetVersion })
    ElMessage.success(`已回退到 v${targetVersion}`)
    openDocDetail(docDetail.value)
  } catch { ElMessage.error('回退失败') } finally { rollingBack.value = false }
}

async function doReprocess() {
  if (!docDetail.value) return
  await ElMessageBox.confirm('确定重新处理？当前版本将自动快照保存，然后重新走清洗/分块/向量化流程。', '重新处理', { type: 'warning' })
  reprocessing.value = true
  try {
    await knowledgeV2Api.reprocess(docDetail.value.document_id)
    ElMessage.success('已提交重新处理，请稍后刷新查看')
  } catch { ElMessage.error('重新处理失败') } finally { reprocessing.value = false }
}

async function doDeleteDoc(doc) {
  await ElMessageBox.confirm(`确定删除文档「${doc.title}」？`, '确认', { type: 'warning' })
  try {
    await knowledgeV2Api.deleteDocument(doc.document_id)
    ElMessage.success('已删除')
    openLibrary(currentLib.value)
  } catch { ElMessage.error('删除失败') }
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  tab.value = 'search'
  searching.value = true
  searchDone.value = false
  searchMeta.value = null
  try {
    const payload = { query: searchQuery.value, top_k: 10, search_mode: searchMode.value }
    if (searchKbIds.value.length) payload.kb_ids = searchKbIds.value
    const r = await knowledgeV2Api.search(payload)
    searchResults.value = r?.hits ?? []
    searchMeta.value = {
      confidence: r?.confidence ?? 'none',
      confidence_score: r?.confidence_score ?? 0,
      ambiguous: r?.ambiguous ?? false,
      suggestion: r?.suggestion ?? 'transfer_human',
      reranked: r?.reranked ?? false,
      search_mode: r?.search_mode ?? searchMode.value,
      degraded: r?.degraded ?? false,
      degraded_reason: r?.degraded_reason,
      elapsed_ms: r?.elapsed_ms ?? 0,
    }
    searchDone.value = true
  } catch { searchResults.value = []; searchMeta.value = null; searchDone.value = true } finally { searching.value = false }
}

async function loadStats() {
  try { stats.value = await knowledgeV2Api.getStats() ?? {} } catch { stats.value = {} }
}

// §4.3 #6：chip 触发检索
function useSuggested(q) {
  searchQuery.value = q
  doSearch()
}

// §4.3 #5：hit 点击进入文档详情
async function openHitDoc(hit) {
  if (!hit?.document_id) return
  await openDocDetail({ document_id: hit.document_id })
}

onMounted(loadLibraries)
</script>

<style scoped>
.kb2__toolbar { display: flex; align-items: center; justify-content: space-between; padding: var(--v2-space-2) var(--v2-space-3); margin-bottom: var(--v2-space-3); background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); flex-wrap: wrap; gap: 8px; }
.kb2__tb-left { display: flex; align-items: center; gap: var(--v2-space-2); }
.kb2__title { font-size: var(--v2-text-md); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; }
.kb2__count { font-size: var(--v2-text-xs); padding: 0 6px; background: var(--v2-bg-sunken); color: var(--v2-text-3); border-radius: var(--v2-radius-sm); }
.kb2__tb-actions { display: flex; align-items: center; gap: 8px; }

.kb2__tabs { display: flex; gap: 2px; margin-bottom: var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); padding: 2px; }
.kb2__tab { padding: 6px 16px; font-size: 12px; color: var(--v2-text-3); cursor: pointer; border-radius: var(--v2-radius-sm); transition: all var(--v2-trans-fast); }
.kb2__tab:hover { color: var(--v2-text-1); }
.kb2__tab--active { background: var(--v2-bg-card); color: var(--v2-brand-primary); font-weight: var(--v2-font-semibold); box-shadow: 0 1px 3px rgba(0,0,0,.08); }

.kb2__panel { background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: var(--v2-radius-lg); padding: var(--v2-space-4); min-height: 400px; }

.kb2__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--v2-space-3); }
.kb2__card { padding: var(--v2-space-3); background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); cursor: pointer; transition: all var(--v2-trans-fast); position: relative; }
.kb2__card:hover { border-color: var(--v2-brand-primary); box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.kb2__card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.kb2__card-icon { font-size: 18px; }
.kb2__card-name { font-size: 13px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); flex: 1; }
.kb2__domain-chip { font-size: 9px; padding: 1px 6px; background: var(--v2-ai-purple-bg); color: var(--v2-ai-purple); border-radius: 3px; flex-shrink: 0; }
.kb2__card-desc { font-size: 11px; color: var(--v2-text-3); margin-bottom: 8px; line-height: 1.4; }
.kb2__card-foot { display: flex; gap: 12px; font-size: 10px; color: var(--v2-text-4); }
.kb2__card-actions { position: absolute; top: 8px; right: 8px; opacity: 0; transition: opacity var(--v2-trans-fast); }
.kb2__card:hover .kb2__card-actions { opacity: 1; }

.kb2__docs { margin-top: var(--v2-space-4); }
.kb2__docs-head { display: flex; align-items: center; gap: 12px; margin-bottom: var(--v2-space-3); }
.kb2__docs-head h3 { font-size: var(--v2-text-sm); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; flex: 1; }

.kb2__st { font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: var(--v2-font-medium); }
.kb2__st--ready { background: var(--v2-success-bg); color: var(--v2-success-text); }
.kb2__st--processing { background: #fef3c7; color: #92400e; }
.kb2__st--pending { background: var(--v2-bg-sunken); color: var(--v2-text-4); }
.kb2__st--failed { background: var(--v2-error-bg); color: var(--v2-error-text); }

.kb2__search-bar { display: flex; gap: 8px; margin-bottom: var(--v2-space-4); }
.kb2__results { display: flex; flex-direction: column; gap: var(--v2-space-3); }
.kb2__hit { padding: var(--v2-space-3); background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); }
.kb2__hit-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.kb2__hit-rank { font-size: 11px; font-weight: var(--v2-font-semibold); color: var(--v2-brand-primary); }
.kb2__hit-score { font-size: 10px; padding: 0 5px; background: var(--v2-success-bg); color: var(--v2-success-text); border-radius: 3px; }
.kb2__hit-mode { font-size: 9px; padding: 0 4px; background: var(--v2-bg-sunken); color: var(--v2-text-4); border-radius: 3px; }
.kb2__hit-rerank { font-size: 9px; padding: 0 4px; background: #ede9fe; color: #6d28d9; border-radius: 3px; }
.kb2__hit-content { font-size: 13px; color: var(--v2-text-1); line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.kb2__hit-meta { margin-top: 4px; font-size: 10px; color: var(--v2-text-4); display: flex; gap: 12px; }

.kb2__search-summary { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; margin-bottom: 12px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); flex-wrap: wrap; gap: 8px; }
.kb2__summary-left { display: flex; align-items: center; gap: 8px; }
.kb2__summary-right { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--v2-text-3); }
.kb2__conf-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.kb2__conf--high { background: #dcfce7; color: #166534; }
.kb2__conf--medium { background: #fef3c7; color: #92400e; }
.kb2__conf--low { background: #fee2e2; color: #991b1b; }
.kb2__conf--none { background: var(--v2-bg-sunken); color: var(--v2-text-4); }
.kb2__conf--ambiguous { background: #fef3c7; color: #92400e; }
.kb2__conf-score { font-size: 12px; font-weight: 600; color: var(--v2-text-1); }
.kb2__conf-ambiguous { font-size: 10px; color: #d97706; }
.kb2__rerank-tag { font-size: 9px; padding: 1px 5px; background: #ede9fe; color: #6d28d9; border-radius: 3px; }
.kb2__suggestion { font-size: 11px; padding: 2px 8px; background: var(--v2-bg-card); border: 1px solid var(--v2-border-2); border-radius: 4px; color: var(--v2-text-2); }
.kb2__search-mode-tag { font-size: 9px; padding: 1px 5px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-2); color: var(--v2-text-4); border-radius: 3px; }
.kb2__search-elapsed { font-size: 10px; color: var(--v2-text-4); }

.kb2__search-loading { padding: 20px 0; }
.kb2__search-loading-tip { text-align: center; margin-top: 12px; font-size: 12px; color: var(--v2-text-4); }

.kb2__stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--v2-space-4); }
.kb2__stat-card { text-align: center; padding: var(--v2-space-6) var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); }
.kb2__stat-num { font-size: 32px; font-weight: var(--v2-font-bold); color: var(--v2-brand-primary); }
.kb2__stat-label { font-size: 12px; color: var(--v2-text-3); margin-top: 4px; }

.kb2__nil { padding: var(--v2-space-8); text-align: center; font-size: 12px; color: var(--v2-text-4); }

.kb2__doc-content { max-height: 200px; overflow-y: auto; padding: 12px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-sm); font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-all; color: var(--v2-text-1); }
.kb2__doc-content--raw { color: var(--v2-text-3); }

.kb2__chunk-item { padding: 10px 12px; margin-bottom: 8px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-sm); }
.kb2__chunk-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.kb2__chunk-idx { font-size: 11px; font-weight: var(--v2-font-semibold); color: var(--v2-brand-primary); }
.kb2__chunk-type { font-size: 9px; padding: 1px 5px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-2); color: var(--v2-text-3); border-radius: 3px; }
.kb2__chunk-tokens { font-size: 9px; color: var(--v2-text-4); }
.kb2__chunk-embed { font-size: 9px; padding: 1px 5px; border-radius: 3px; }
.kb2__chunk-text { font-size: 12px; color: var(--v2-text-2); line-height: 1.6; white-space: pre-wrap; word-break: break-all; }

.kb2__detail-tabs { display: flex; align-items: center; gap: 2px; margin: 12px 0 8px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-md); padding: 2px; }
.kb2__detail-tab { padding: 5px 14px; font-size: 12px; color: var(--v2-text-3); cursor: pointer; border-radius: var(--v2-radius-sm); transition: all var(--v2-trans-fast); }
.kb2__detail-tab:hover { color: var(--v2-text-1); }
.kb2__detail-tab--active { background: var(--v2-bg-card); color: var(--v2-brand-primary); font-weight: var(--v2-font-semibold); box-shadow: 0 1px 3px rgba(0,0,0,.08); }

.kb2__ver-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.kb2__ver-item { padding: 10px 12px; background: var(--v2-bg-sunken); border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-sm); }
.kb2__ver-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.kb2__ver-tag { font-size: 12px; font-weight: var(--v2-font-semibold); color: var(--v2-brand-primary); background: var(--v2-ai-purple-bg); padding: 1px 8px; border-radius: 3px; }
.kb2__ver-time { font-size: 11px; color: var(--v2-text-3); }
.kb2__ver-meta { font-size: 10px; color: var(--v2-text-4); }
.kb2__ver-by { font-size: 10px; color: var(--v2-text-4); margin-left: auto; }
.kb2__chunks-list { margin-top: 8px; }

/* §4.3 #1 lucide 图标承载 */
.kb2__card-icon { color: var(--v2-brand-primary); flex-shrink: 0; }

/* §4.3 #8 health badge + 相对时间 */
.kb2__card-health { font-size: 9px; padding: 1px 5px; border-radius: 3px; font-weight: var(--v2-font-medium); flex-shrink: 0; margin-left: auto; }
.kb2__card-health--ok       { background: var(--v2-success-bg); color: var(--v2-success-text); }
.kb2__card-health--empty    { background: var(--v2-bg-sunken);  color: var(--v2-text-4); border: 1px solid var(--v2-border-2); }
.kb2__card-health--disabled { background: var(--v2-error-bg);   color: var(--v2-error-text); }
.kb2__card-time { margin-left: auto; font-size: 10px; color: var(--v2-text-4); }

/* §4.3 #6 空搜索引导 chip */
.kb2__chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 8px 12px; margin-bottom: 12px; background: var(--v2-bg-sunken); border: 1px dashed var(--v2-border-2); border-radius: var(--v2-radius-md); }
.kb2__chips-label { font-size: 11px; color: var(--v2-text-4); margin-right: 4px; }
.kb2__chip { padding: 3px 10px; font-size: 11px; color: var(--v2-text-2); background: var(--v2-bg-card); border: 1px solid var(--v2-border-1); border-radius: 999px; cursor: pointer; transition: all var(--v2-trans-fast); }
.kb2__chip:hover { border-color: var(--v2-brand-primary); color: var(--v2-brand-primary); background: var(--v2-brand-bg); }

/* §4.3 #5 hit 可点击 */
.kb2__hit--clickable { cursor: pointer; }
.kb2__hit--clickable:hover { border-color: var(--v2-brand-primary); box-shadow: 0 2px 8px rgba(0,0,0,.06); }

/* §4.3 #4 降级 inline badge */
.kb2__degraded-badge { font-size: 10px; padding: 1px 6px; background: #fef3c7; color: #92400e; border-radius: 3px; font-weight: var(--v2-font-medium); cursor: help; }

/* §4.3 #7 chunk 折叠 */
.kb2__chunk-text--collapsed { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.kb2__chunk-toggle { margin-left: auto; font-size: 10px; color: var(--v2-brand-primary); cursor: pointer; user-select: none; }
.kb2__chunk-toggle:hover { text-decoration: underline; }
</style>
