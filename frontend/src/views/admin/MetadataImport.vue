<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, DocumentAdd, Download, UploadFilled } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'

const selectedFile = ref(null)
const uploading = ref(false)
const committing = ref(false)
const templateDownloading = ref(false)
const templateFormat = ref('xlsx')
const result = ref(null)
const templateFormats = [
  { label: 'Excel xlsx', value: 'xlsx' },
  { label: 'CSV', value: 'csv' },
  { label: 'JSON', value: 'json' },
  { label: 'Excel xlsm', value: 'xlsm' }
]
const templateExtensions = new Set(templateFormats.map((item) => item.value))

const canCommit = computed(() => Boolean(selectedFile.value && result.value && result.value.error_rows === 0))
const hasResult = computed(() => Boolean(result.value))
const templateFilename = computed(() => {
  const extension = templateExtensions.has(templateFormat.value) ? templateFormat.value : 'xlsx'
  return `metadata-import-template.${extension}`
})

function handleFileChange(file) {
  selectedFile.value = file.raw || file
  result.value = null
}

function buildFormData() {
  const data = new FormData()
  data.append('file', selectedFile.value)
  return data
}

async function previewImport() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择 CSV、JSON 或 Excel 文件')
    return
  }
  uploading.value = true
  try {
    result.value = await galleryApi.importMetadata(buildFormData(), true)
    if (result.value.error_rows) {
      ElMessage.warning(`预检完成，有 ${result.value.error_rows} 行需要处理`)
    } else {
      ElMessage.success('预检通过，可以导入')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '预检失败')
  } finally {
    uploading.value = false
  }
}

async function commitImport() {
  if (!canCommit.value) return
  committing.value = true
  try {
    result.value = await galleryApi.importMetadata(buildFormData(), false)
    ElMessage.success('导入完成')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '导入失败')
  } finally {
    committing.value = false
  }
}

async function downloadTemplate() {
  templateDownloading.value = true
  try {
    const blob = await galleryApi.metadataImportTemplate(templateFormat.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = templateFilename.value
    document.body.appendChild(link)
    link.click()
    window.setTimeout(() => {
      link.remove()
      URL.revokeObjectURL(url)
    }, 1000)
    ElMessage.success('模板已下载')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '模板下载失败')
  } finally {
    templateDownloading.value = false
  }
}
</script>

<template>
  <div class="admin-card metadata-import-page">
    <div class="metadata-import-layout">
      <section class="metadata-import-panel">
        <div class="section-title">
          <div>
            <h2>导入文件</h2>
            <span class="muted">先下载模板填写，再上传预检。支持 CSV、JSON、XLSX、XLSM。</span>
          </div>
        </div>
        <div class="metadata-template-toolbar">
          <el-select v-model="templateFormat" style="width: 150px">
            <el-option v-for="item in templateFormats" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-button :icon="Download" :loading="templateDownloading" @click="downloadTemplate">下载模板</el-button>
        </div>
        <el-upload
          drag
          :auto-upload="false"
          :show-file-list="false"
          accept=".csv,.json,.xlsx,.xlsm"
          :on-change="handleFileChange"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">{{ selectedFile ? selectedFile.name : '拖入元数据文件或点击选择' }}</div>
          <template #tip>
            <div class="el-upload__tip">推荐先上传文件预检，确认无错误后再正式导入。</div>
          </template>
        </el-upload>
        <div class="metadata-import-actions">
          <el-button :icon="DocumentAdd" :loading="uploading" :disabled="!selectedFile" @click="previewImport">预检文件</el-button>
          <el-button type="primary" :icon="Check" :loading="committing" :disabled="!canCommit" @click="commitImport">确认导入</el-button>
        </div>
      </section>

      <section class="metadata-import-panel metadata-import-help">
        <div class="section-title">
          <div>
            <h2>匹配规则</h2>
            <span class="muted">导入不会创建新表，直接写入现有作品和角色。</span>
          </div>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="作品字段">`work_name` 必填；`work_original_name`、`work_description`、`work_tagline` 等按需填写。</el-descriptions-item>
          <el-descriptions-item label="角色字段">填写 `character_name` 时会导入角色；留空则只导入作品。</el-descriptions-item>
          <el-descriptions-item label="作品匹配">按 `work_name` 精确匹配，存在则更新，不存在则创建。</el-descriptions-item>
          <el-descriptions-item label="角色匹配">按 `work_name + character_name` 匹配，存在则更新，不存在则创建。</el-descriptions-item>
          <el-descriptions-item label="Excel 支持">支持 `.xlsx/.xlsm`，后端需要安装 `openpyxl`。</el-descriptions-item>
        </el-descriptions>
      </section>
    </div>

    <section v-if="hasResult" class="metadata-import-result">
      <div class="section-title">
        <div>
          <h2>{{ result.dry_run ? '预检结果' : '导入结果' }}</h2>
          <span class="muted">共 {{ result.total_rows }} 行，{{ result.valid_rows }} 行有效，{{ result.error_rows }} 行错误。</span>
        </div>
      </div>
      <div class="stats-grid metadata-import-stats">
        <div class="stat-card">
          <span class="muted">创建作品</span>
          <strong>{{ result.works_created }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">更新作品</span>
          <strong>{{ result.works_updated }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">创建角色</span>
          <strong>{{ result.characters_created }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">更新角色</span>
          <strong>{{ result.characters_updated }}</strong>
        </div>
      </div>
      <el-table :data="result.rows" row-key="row_number">
        <el-table-column prop="row_number" label="行" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ok' ? 'success' : 'danger'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" width="160" />
        <el-table-column prop="work_name" label="作品" min-width="180" />
        <el-table-column prop="character_name" label="角色" min-width="180" />
        <el-table-column prop="message" label="说明" min-width="220" />
      </el-table>
    </section>
  </div>
</template>
