<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Key, Link, Lock, Refresh, Search } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'

const tagLabels = {
  auth: '鉴权',
  install: '首次安装',
  images: '图片',
  'upload-tasks': '上传任务',
  imports: '批量导入',
  works: '作品',
  characters: '角色',
  tags: '标签兼容',
  search: '搜索',
  stats: '统计',
  settings: '设置',
  system: '系统',
  storage: '文件访问',
  health: '存活检查'
}

const methodOrder = {
  get: 1,
  post: 2,
  put: 3,
  patch: 4,
  delete: 5
}

const schema = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedTag = ref('all')
const keyword = ref('')

const tagDocs = computed(() => schema.value?.tags || [])

const operations = computed(() => {
  const paths = schema.value?.paths || {}
  return Object.entries(paths).flatMap(([path, pathItem]) => {
    return Object.entries(pathItem)
      .filter(([method]) => ['get', 'post', 'put', 'patch', 'delete'].includes(method))
      .map(([method, operation]) => ({
        method,
        path,
        id: `${method.toUpperCase()} ${path}`,
        tags: operation.tags?.length ? operation.tags : ['default'],
        summary: operation.summary || '未命名接口',
        description: operation.description || '',
        parameters: operation.parameters || [],
        requestBody: operation.requestBody,
        responses: operation.responses || {},
        protected: Array.isArray(operation.security) && operation.security.length > 0
      }))
  }).sort((left, right) => {
    const tagDiff = tagIndex(left.tags[0]) - tagIndex(right.tags[0])
    if (tagDiff) return tagDiff
    if (left.path !== right.path) return left.path.localeCompare(right.path)
    return (methodOrder[left.method] || 99) - (methodOrder[right.method] || 99)
  })
})

const tagStats = computed(() => {
  const stats = new Map()
  operations.value.forEach((operation) => {
    operation.tags.forEach((tag) => {
      stats.set(tag, (stats.get(tag) || 0) + 1)
    })
  })
  return stats
})

const visibleTagDocs = computed(() => tagDocs.value.filter((tag) => (tagStats.value.get(tag.name) || 0) > 0))

const filteredOperations = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return operations.value.filter((operation) => {
    const matchesTag = selectedTag.value === 'all' || operation.tags.includes(selectedTag.value)
    if (!matchesTag) return false
    if (!query) return true
    return [
      operation.path,
      operation.method,
      operation.summary,
      operation.description,
      tagName(operation.tags[0])
    ].some((value) => String(value || '').toLowerCase().includes(query))
  })
})

const protectedCount = computed(() => operations.value.filter((operation) => operation.protected).length)

function tagIndex(tag) {
  const index = tagDocs.value.findIndex((item) => item.name === tag)
  return index === -1 ? 999 : index
}

function tagName(tag) {
  return tagLabels[tag] || tag || '其他'
}

function tagDescription(tag) {
  return tagDocs.value.find((item) => item.name === tag)?.description || ''
}

function requestContentTypes(operation) {
  return Object.keys(operation.requestBody?.content || {})
}

function responseEntries(operation) {
  return Object.entries(operation.responses || {}).map(([code, response]) => ({
    code,
    description: responseDescription(response.description)
  }))
}

function responseDescription(description) {
  const translations = {
    'Successful Response': '请求成功',
    'Validation Error': '参数校验失败'
  }
  return translations[description] || description || '无说明'
}

function parameterType(parameter) {
  const schemaNode = parameter.schema || {}
  if (schemaNode.type) return schemaNode.type
  if (schemaNode.anyOf) return schemaNode.anyOf.map((item) => item.type || item.$ref || 'object').join(' / ')
  if (schemaNode.$ref) return schemaNode.$ref.split('/').pop()
  return 'object'
}

function sampleBody(operation) {
  const contents = operation.requestBody?.content || {}
  const jsonContent = contents['application/json']
  const multipartContent = contents['multipart/form-data']
  const firstExample = jsonContent?.examples && Object.values(jsonContent.examples)[0]?.value
  if (firstExample) return JSON.stringify(firstExample, null, 2)
  if (jsonContent) return '{\n  "key": "value"\n}'
  if (multipartContent) return '-F "file=@example.webp"'
  return ''
}

function curlExample(operation) {
  const method = operation.method.toUpperCase()
  const lines = [`curl -X ${method} "$BASE_URL${operation.path}"`]
  if (operation.protected) {
    lines.push('  -H "Authorization: Bearer $AGMS_API_KEY"')
  }
  const contentTypes = requestContentTypes(operation)
  if (contentTypes.includes('application/json')) {
    lines.push('  -H "Content-Type: application/json"')
    lines.push(`  -d '${sampleBody(operation).replace(/\n/g, '\\n')}'`)
  } else if (contentTypes.includes('multipart/form-data')) {
    lines.push('  -F "file=@example.webp"')
  }
  return lines.join(' \\\n')
}

function openRawDocs() {
  window.open('/api-docs', '_blank', 'noopener,noreferrer')
}

async function copyCurl(operation) {
  try {
    await navigator.clipboard.writeText(curlExample(operation))
    ElMessage.success('已复制 curl 示例')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function loadDocs() {
  loading.value = true
  errorMessage.value = ''
  try {
    schema.value = await galleryApi.apiDocs()
    if (selectedTag.value !== 'all' && !tagStats.value.has(selectedTag.value)) {
      selectedTag.value = 'all'
    }
  } catch (error) {
    errorMessage.value = error?.response?.data?.detail || error?.message || '无法读取 API 文档'
  } finally {
    loading.value = false
  }
}

onMounted(loadDocs)
</script>

<template>
  <div class="api-docs-standalone">
    <header class="api-docs-standalone__header">
      <RouterLink class="admin-brand" to="/admin">
        <img class="brand-avatar" src="/avatar.webp" alt="Anime Gallery" />
        <span class="brand-copy">
          <strong>Anime Gallery</strong>
          <small>API reference</small>
        </span>
      </RouterLink>
      <div class="api-docs-standalone__actions">
        <el-button @click="$router.push('/admin')">返回后台</el-button>
        <el-button type="primary" :icon="Link" @click="openRawDocs">打开交互文档</el-button>
      </div>
    </header>

    <div class="admin-card api-docs-page" v-loading="loading">
      <section class="admin-inline-hero api-docs-hero">
      <div>
        <span class="hero-eyebrow">OpenAPI</span>
        <h2>API 文档</h2>
        <p class="muted">后台集成、运维脚本和接口排障使用的中文接口说明。</p>
      </div>
      <div class="api-docs-hero__actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadDocs">刷新</el-button>
      </div>
      </section>

    <el-alert
      v-if="errorMessage"
      class="api-docs-alert"
      type="error"
      :closable="false"
      :title="errorMessage"
      show-icon
    />

      <template v-if="schema">
      <div class="api-docs-summary">
        <div class="api-docs-summary__item">
          <el-icon><Document /></el-icon>
          <span>接口数量</span>
          <strong>{{ operations.length }}</strong>
        </div>
        <div class="api-docs-summary__item">
          <el-icon><Search /></el-icon>
          <span>接口分组</span>
          <strong>{{ visibleTagDocs.length }}</strong>
        </div>
        <div class="api-docs-summary__item">
          <el-icon><Lock /></el-icon>
          <span>需鉴权</span>
          <strong>{{ protectedCount }}</strong>
        </div>
        <div class="api-docs-summary__item">
          <el-icon><Key /></el-icon>
          <span>版本</span>
          <strong>{{ schema.info?.version || '-' }}</strong>
        </div>
      </div>

      <section class="api-auth-panel">
        <div>
          <strong>鉴权方式</strong>
          <p class="muted">
            浏览器后台使用管理员 Cookie；运维脚本使用 <code>Authorization: Bearer $AGMS_API_KEY</code>。
            Cookie 会话发起写入请求时，还需要提交匹配的 <code>X-CSRF-Token</code>。
          </p>
        </div>
      </section>

      <div class="api-docs-toolbar">
        <el-input
          v-model="keyword"
          clearable
          :prefix-icon="Search"
          placeholder="搜索接口路径、摘要或说明"
        />
      </div>

      <div class="api-docs-layout">
        <aside class="api-docs-sidebar">
          <button
            type="button"
            class="api-docs-tag"
            :class="{ 'is-active': selectedTag === 'all' }"
            @click="selectedTag = 'all'"
          >
            <span>全部接口</span>
            <strong>{{ operations.length }}</strong>
          </button>
          <button
            v-for="tag in visibleTagDocs"
            :key="tag.name"
            type="button"
            class="api-docs-tag"
            :class="{ 'is-active': selectedTag === tag.name }"
            @click="selectedTag = tag.name"
          >
            <span>{{ tagName(tag.name) }}</span>
            <strong>{{ tagStats.get(tag.name) || 0 }}</strong>
          </button>
        </aside>

        <main class="api-docs-main">
          <header class="api-docs-section-head">
            <div>
              <strong>{{ selectedTag === 'all' ? '全部接口' : tagName(selectedTag) }}</strong>
              <p class="muted">{{ selectedTag === 'all' ? '按业务分组排列，支持关键词筛选。' : tagDescription(selectedTag) }}</p>
            </div>
            <span class="api-docs-count">{{ filteredOperations.length }} 个接口</span>
          </header>

          <el-empty v-if="!filteredOperations.length" description="没有匹配的接口" />

          <article
            v-for="operation in filteredOperations"
            :key="operation.id"
            class="api-operation-card"
          >
            <header class="api-operation-card__head">
              <div class="api-endpoint-line">
                <span class="api-method" :class="`api-method--${operation.method}`">{{ operation.method.toUpperCase() }}</span>
                <code>{{ operation.path }}</code>
              </div>
              <el-tag :type="operation.protected ? 'warning' : 'success'" effect="plain">
                {{ operation.protected ? '需要鉴权' : '免登录' }}
              </el-tag>
            </header>

            <div class="api-operation-card__body">
              <h3>{{ operation.summary }}</h3>
              <p v-if="operation.description" class="muted">{{ operation.description }}</p>

              <div class="api-meta-row">
                <span>分组：{{ operation.tags.map(tagName).join('、') }}</span>
                <span v-if="requestContentTypes(operation).length">
                  请求体：{{ requestContentTypes(operation).join('、') }}
                </span>
              </div>

              <div v-if="operation.parameters.length" class="api-table-wrap">
                <table class="api-param-table">
                  <thead>
                    <tr>
                      <th>参数</th>
                      <th>位置</th>
                      <th>类型</th>
                      <th>必填</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="parameter in operation.parameters" :key="`${operation.id}-${parameter.in}-${parameter.name}`">
                      <td><code>{{ parameter.name }}</code></td>
                      <td>{{ parameter.in }}</td>
                      <td>{{ parameterType(parameter) }}</td>
                      <td>{{ parameter.required ? '是' : '否' }}</td>
                      <td>{{ parameter.description || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="api-response-list">
                <span
                  v-for="response in responseEntries(operation)"
                  :key="`${operation.id}-${response.code}`"
                  class="api-response-chip"
                >
                  <strong>{{ response.code }}</strong>
                  {{ response.description }}
                </span>
              </div>

              <div class="api-curl-box">
                <div class="api-curl-box__head">
                  <span>curl 示例</span>
                  <el-button size="small" text @click="copyCurl(operation)">复制</el-button>
                </div>
                <pre><code>{{ curlExample(operation) }}</code></pre>
              </div>
            </div>
          </article>
        </main>
      </div>
      </template>
    </div>
  </div>
</template>
