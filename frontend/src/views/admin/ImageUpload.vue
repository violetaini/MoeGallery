<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Close, Delete, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'
import { imageUploadAccept, imageUploadSupportText } from '../../constants/uploadFormats'
import { mergeSelectedOptions } from '../../utils/remoteOptions'

const fileList = ref([])
const nativeFileInput = ref(null)
const works = ref([])
const characters = ref([])
const uploading = ref(false)
const checkingDuplicates = ref(false)
const taskItems = ref([])
const taskTotal = ref(0)
const taskPage = ref(1)
const taskPageSize = 20
const taskStatusFilter = ref('')
const selectedTaskIds = ref([])
const taskLoading = ref(false)
const taskActionLoading = ref(false)
const taskPollingTimer = ref(null)
let taskPollingGeneration = 0
let taskRequestSeq = 0
let taskLoadingSeq = 0
const previewItems = ref([])
const previewPage = ref(1)
const previewPageSize = 12
const activePreviewUid = ref(null)
const optionLoading = reactive({ works: false, characters: false })
const optionRequestSeq = { works: 0, characters: 0 }
const form = reactive({
  work_ids: [],
  character_ids: [],
  rating: 'safe',
  is_public: true,
  source_url: '',
  artist_name: ''
})
const totalFiles = computed(() => previewItems.value.length)
const totalPreviewPages = computed(() => Math.max(1, Math.ceil(totalFiles.value / previewPageSize)))
const pagedPreviewItems = computed(() => {
  const start = (previewPage.value - 1) * previewPageSize
  return previewItems.value.slice(start, start + previewPageSize)
})
const activePreviewIndex = computed(() => previewItems.value.findIndex((item) => item.uid === activePreviewUid.value))
const activePreviewItem = computed(() => (
  activePreviewIndex.value >= 0 ? previewItems.value[activePreviewIndex.value] : null
))
const activeTasks = computed(() => taskItems.value.filter((item) => ['queued', 'processing', 'retry_wait'].includes(item.status)))
const completedTasks = computed(() => taskItems.value.filter((item) => item.status === 'success'))
const failedTasks = computed(() => taskItems.value.filter((item) => item.status === 'failed'))
const allPageTasksSelected = computed(() => (
  taskItems.value.length > 0 && taskItems.value.every((item) => selectedTaskIds.value.includes(item.id))
))
const taskStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'queued', label: '排队中' },
  { value: 'processing', label: '处理中' },
  { value: 'retry_wait', label: '等待重试' },
  { value: 'success', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'canceled', label: '已取消' }
]
const duplicateHashConcurrency = 8
const previewConcurrency = 6
const previewQueue = []
let activePreviewRequests = 0
const uploadingLabel = computed(() => {
  if (checkingDuplicates.value) return '校验重复中'
  if (uploading.value) return '提交任务中'
  return '开始批量上传'
})

function taskStatusLabel(status) {
  if (status === 'queued') return '排队中'
  if (status === 'processing') return '处理中'
  if (status === 'retry_wait') return '等待重试'
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'canceled') return '已取消'
  return status
}

function taskStatusType(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'processing' || status === 'retry_wait') return 'warning'
  return 'info'
}

function formatBytes(size) {
  const value = Number(size || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function formatTaskTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false })
}

function canRetryTask(task) {
  return ['failed', 'retry_wait'].includes(task.status) && task.staged_file_available
}

function canCancelTask(task) {
  return ['queued', 'processing', 'retry_wait'].includes(task.status) && !task.cancel_requested
}

function canDeleteTask(task) {
  return ['success', 'failed', 'canceled'].includes(task.status)
}

function toggleTaskSelection(taskId, selected) {
  const next = new Set(selectedTaskIds.value)
  if (selected) next.add(taskId)
  else next.delete(taskId)
  selectedTaskIds.value = [...next]
}

function toggleAllPageTasks(selected) {
  const next = new Set(selectedTaskIds.value)
  taskItems.value.forEach((task) => {
    if (selected) next.add(task.id)
    else next.delete(task.id)
  })
  selectedTaskIds.value = [...next]
}

function revokePreview(url) {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url)
  }
}

function cleanupPreviewItems() {
  previewQueue.length = 0
  previewItems.value.forEach((item) => revokePreview(item.previewUrl))
  previewItems.value = []
  activePreviewUid.value = null
  previewPage.value = 1
}

function stopTaskPolling() {
  taskPollingGeneration += 1
  if (taskPollingTimer.value) {
    window.clearTimeout(taskPollingTimer.value)
    taskPollingTimer.value = null
  }
}

async function loadWorks(query = '') {
  const seq = ++optionRequestSeq.works
  optionLoading.works = true
  try {
    const value = query.trim()
    const data = await galleryApi.works({ page_size: 100, ...(value ? { q: value } : {}) })
    if (seq !== optionRequestSeq.works) return
    works.value = mergeSelectedOptions(works.value, form.work_ids, data.items)
  } catch (error) {
    if (seq === optionRequestSeq.works) ElMessage.error(error?.response?.data?.detail || '加载作品选项失败')
  } finally {
    if (seq === optionRequestSeq.works) optionLoading.works = false
  }
}

async function loadCharacters(query = '') {
  const seq = ++optionRequestSeq.characters
  optionLoading.characters = true
  try {
    const value = query.trim()
    const data = await galleryApi.characters({ page_size: 100, ...(value ? { q: value } : {}) })
    if (seq !== optionRequestSeq.characters) return
    characters.value = mergeSelectedOptions(characters.value, form.character_ids, data.items)
  } catch (error) {
    if (seq === optionRequestSeq.characters) ElMessage.error(error?.response?.data?.detail || '加载角色选项失败')
  } finally {
    if (seq === optionRequestSeq.characters) optionLoading.characters = false
  }
}

async function loadOptions() {
  await Promise.all([loadWorks(), loadCharacters()])
}

async function createPreview(item) {
  try {
    const blob = await galleryApi.previewUploadImage(item.raw)
    if (!previewItems.value.some((candidate) => candidate.uid === item.uid)) return
    const url = URL.createObjectURL(blob)
    if (!previewItems.value.some((candidate) => candidate.uid === item.uid)) {
      revokePreview(url)
      return
    }
    item.previewUrl = url
    item.previewStatus = 'ready'
  } catch (error) {
    item.previewStatus = 'error'
    item.errorMessage = error?.response?.data?.detail || '预览失败'
  }
}

function pumpPreviewQueue() {
  while (activePreviewRequests < previewConcurrency && previewQueue.length) {
    const item = previewQueue.shift()
    if (!item || !previewItems.value.some((candidate) => candidate.uid === item.uid)) continue
    activePreviewRequests += 1
    item.previewStatus = 'loading'
    void createPreview(item).finally(() => {
      activePreviewRequests -= 1
      pumpPreviewQueue()
    })
  }
}

function enqueuePreview(item) {
  item.previewStatus = 'queued'
  previewQueue.push(item)
  pumpPreviewQueue()
}

function syncPreviewItems(files) {
  const nextByUid = new Map(files.map((file) => [file.uid, file]))
  previewItems.value = previewItems.value.filter((item) => {
    if (nextByUid.has(item.uid)) {
      return true
    }
    revokePreview(item.previewUrl)
    return false
  })

  const existing = new Set(previewItems.value.map((item) => item.uid))
  for (const file of files) {
    if (existing.has(file.uid) || !file.raw) continue
    const previewItem = reactive({
      uid: file.uid,
      name: file.name,
      size: file.size || file.raw.size || 0,
      extension: `.${String(file.name || '').split('.').pop() || ''}`.toLowerCase(),
      raw: file.raw,
      previewUrl: '',
      previewStatus: 'queued',
      errorMessage: ''
    })
    previewItems.value.push(previewItem)
    enqueuePreview(previewItem)
  }

  if (activePreviewUid.value && !previewItems.value.some((item) => item.uid === activePreviewUid.value)) {
    activePreviewUid.value = null
  }
  if (previewPage.value > totalPreviewPages.value) {
    previewPage.value = totalPreviewPages.value
  }
}

function handleFileChange(_file, files) {
  syncPreviewItems(files)
}

function openNativePicker() {
  nativeFileInput.value?.click()
}

function nativeFileToUploadFile(file) {
  const uid = `${Date.now()}-${Math.random().toString(16).slice(2)}-${file.name}`
  return {
    name: file.name,
    size: file.size,
    uid,
    raw: file
  }
}

function handleNativeFiles(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) {
    return
  }
  const nextFiles = [...fileList.value, ...files.map(nativeFileToUploadFile)]
  fileList.value = nextFiles
  syncPreviewItems(nextFiles)
  event.target.value = ''
}

function handleFileRemove(file, files) {
  const target = previewItems.value.find((item) => item.uid === file.uid)
  if (target) {
    revokePreview(target.previewUrl)
  }
  syncPreviewItems(files)
}

function clearSelectedFiles() {
  cleanupPreviewItems()
  fileList.value = []
}

function removePreviewItem(uid) {
  const nextFiles = fileList.value.filter((file) => file.uid !== uid)
  const target = previewItems.value.find((item) => item.uid === uid)
  if (target) {
    revokePreview(target.previewUrl)
  }
  fileList.value = nextFiles
  syncPreviewItems(nextFiles)
}

function openPreview(item) {
  activePreviewUid.value = item.uid
}

function closePreview() {
  activePreviewUid.value = null
}

function showPreviousPreview() {
  if (activePreviewIndex.value <= 0) return
  activePreviewUid.value = previewItems.value[activePreviewIndex.value - 1].uid
}

function showNextPreview() {
  if (activePreviewIndex.value < 0 || activePreviewIndex.value >= previewItems.value.length - 1) return
  activePreviewUid.value = previewItems.value[activePreviewIndex.value + 1].uid
}

function removeActivePreviewItem() {
  if (!activePreviewItem.value) return
  const currentIndex = activePreviewIndex.value
  const currentUid = activePreviewItem.value.uid
  removePreviewItem(currentUid)
  const nextItem = previewItems.value[currentIndex] || previewItems.value[currentIndex - 1] || null
  activePreviewUid.value = nextItem?.uid || null
}

function buildUploadFormData(files, mergeDuplicateRelations = false) {
  const data = new FormData()
  files.forEach((file) => data.append('files', file.raw))
  data.append('work_ids', form.work_ids.join(','))
  data.append('character_ids', form.character_ids.join(','))
  data.append('rating', form.rating)
  data.append('is_public', String(form.is_public))
  data.append('merge_duplicate_relations', String(mergeDuplicateRelations))
  if (form.source_url) data.append('source_url', form.source_url)
  if (form.artist_name) data.append('artist_name', form.artist_name)
  return data
}

function bytesToHex(buffer) {
  return Array.from(new Uint8Array(buffer)).map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

async function fileSha256(file) {
  if (!globalThis.crypto?.subtle) {
    throw new Error('当前浏览器环境不支持本地 SHA-256 校验，请使用 localhost/HTTPS 访问后再上传')
  }
  const buffer = await file.arrayBuffer()
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer)
  return bytesToHex(digest)
}

async function mapWithConcurrency(items, concurrency, mapper) {
  const result = new Array(items.length)
  let nextIndex = 0
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex
      nextIndex += 1
      result[currentIndex] = await mapper(items[currentIndex], currentIndex)
    }
  })
  await Promise.all(workers)
  return result
}

async function checkDuplicates(files) {
  checkingDuplicates.value = true
  try {
    const hashes = await mapWithConcurrency(files, duplicateHashConcurrency, async (file) => ({
      filename: file.name,
      sha256: await fileSha256(file.raw)
    }))
    const result = await galleryApi.checkUploadDuplicates({ items: hashes })
    return result.items || []
  } catch (error) {
    const action = await ElMessageBox.confirm(
      '重复校验接口暂时不可用，可以跳过校验直接提交上传。跳过后如果文件已存在，系统仍不会新建重复图片，也不会自动覆盖已有元数据。',
      '重复校验失败',
      {
        type: 'warning',
        confirmButtonText: '跳过校验继续',
        cancelButtonText: '取消上传',
        closeOnClickModal: false
      }
    ).then(() => 'continue').catch(() => 'abort')
    if (action === 'continue') {
      return []
    }
    throw error
  } finally {
    checkingDuplicates.value = false
  }
}

function duplicateMessage(items) {
  const libraryDuplicates = items.filter((item) => item.duplicate)
  const queueDuplicates = items.filter((item) => item.duplicate_in_queue && !item.duplicate)
  const batchDuplicates = items.filter(
    (item) => item.duplicate_in_batch && !item.duplicate && !item.duplicate_in_queue
  )
  const lines = []
  if (libraryDuplicates.length) {
    lines.push(`图库已有 ${libraryDuplicates.length} 张：`)
    libraryDuplicates.slice(0, 8).forEach((item) => {
      const image = item.existing_image
      const name = image?.original_filename || image?.filename || `图片 ID ${image?.id}`
      lines.push(`- ${item.filename} -> ${name}`)
    })
  }
  if (queueDuplicates.length) {
    lines.push(`上传队列中已有 ${queueDuplicates.length} 张：`)
    queueDuplicates.slice(0, 8).forEach((item) => lines.push(`- ${item.filename}`))
  }
  if (batchDuplicates.length) {
    lines.push(`本批次内重复 ${batchDuplicates.length} 张：`)
    batchDuplicates.slice(0, 8).forEach((item) => lines.push(`- ${item.filename}`))
  }
  if (libraryDuplicates.length + queueDuplicates.length + batchDuplicates.length > 8) {
    lines.push('其余重复项请在预览列表中核对。')
  }
  return lines.join('\n')
}

async function resolveDuplicateUpload(files) {
  let items = []
  try {
    items = await checkDuplicates(files)
  } finally {
    checkingDuplicates.value = false
  }
  const duplicateItems = items.filter(
    (item) => item.duplicate || item.duplicate_in_queue || item.duplicate_in_batch
  )
  if (!duplicateItems.length) {
    return { files, mergeDuplicateRelations: false }
  }

  const action = await ElMessageBox.confirm(
    duplicateMessage(duplicateItems),
    '发现重复图片',
    {
      type: 'warning',
      distinguishCancelAndClose: true,
      confirmButtonText: '合并关系后继续',
      cancelButtonText: '跳过重复',
      closeOnClickModal: false
    }
  ).then(() => 'merge').catch((value) => (value === 'cancel' ? 'skip' : 'abort'))

  if (action === 'abort') {
    return null
  }
  if (action === 'merge') {
    return { files, mergeDuplicateRelations: true }
  }

  const duplicateIndexes = new Set(
    items
      .map((item, index) => (
        item.duplicate || item.duplicate_in_queue || item.duplicate_in_batch ? index : -1
      ))
      .filter((index) => index >= 0)
  )
  const nextFiles = files.filter((_file, index) => !duplicateIndexes.has(index))
  if (!nextFiles.length) {
    ElMessage.info('已跳过所有重复图片，没有提交新任务')
    return null
  }
  ElMessage.info(`已跳过 ${files.length - nextFiles.length} 张重复图片`)
  fileList.value = nextFiles
  syncPreviewItems(nextFiles)
  return { files: nextFiles, mergeDuplicateRelations: false }
}

async function submitUpload() {
  if (!fileList.value.length) {
    ElMessage.warning('请选择图片')
    return
  }
  uploading.value = true
  try {
    const duplicateDecision = await resolveDuplicateUpload(fileList.value)
    if (!duplicateDecision) {
      return
    }
    const data = buildUploadFormData(duplicateDecision.files, duplicateDecision.mergeDuplicateRelations)
    const result = await galleryApi.createUploadTasks(data)
    const submittedCount = result.items?.length || 0
    taskPage.value = 1
    taskStatusFilter.value = ''
    ElMessage.success(`已提交 ${submittedCount} 个上传任务`)
    clearSelectedFiles()
    await loadUploadTasks({ silent: true })
    startTaskPolling()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '上传失败'
    ElMessage.error(Array.isArray(detail) ? detail.map((item) => item.msg || item).join('；') : detail)
  } finally {
    uploading.value = false
    checkingDuplicates.value = false
  }
}

async function loadUploadTasks({ silent = false } = {}) {
  const seq = ++taskRequestSeq
  const requestedPage = taskPage.value
  const requestedStatus = taskStatusFilter.value
  const loadingSeq = silent ? null : ++taskLoadingSeq
  if (loadingSeq !== null) taskLoading.value = true
  try {
    const data = await galleryApi.uploadTasks({
      page: requestedPage,
      page_size: taskPageSize,
      status: requestedStatus || undefined
    })
    if (seq !== taskRequestSeq) return
    taskItems.value = data.items || []
    taskTotal.value = Number(data.total || 0)
    selectedTaskIds.value = selectedTaskIds.value.filter((id) => taskItems.value.some((task) => task.id === id))
  } catch (error) {
    if (!silent && seq === taskRequestSeq) ElMessage.error(error?.response?.data?.detail || '刷新上传任务失败')
  } finally {
    if (loadingSeq !== null && loadingSeq === taskLoadingSeq) taskLoading.value = false
  }
}

async function refreshUploadTasks(generation = taskPollingGeneration) {
  taskPollingTimer.value = null
  await loadUploadTasks({ silent: true })
  if (generation !== taskPollingGeneration) return
  if (activeTasks.value.length) {
    taskPollingTimer.value = window.setTimeout(() => refreshUploadTasks(generation), 2000)
  }
}

function startTaskPolling() {
  stopTaskPolling()
  const generation = taskPollingGeneration
  taskPollingTimer.value = window.setTimeout(() => refreshUploadTasks(generation), 2000)
}

async function changeTaskStatusFilter() {
  taskPage.value = 1
  selectedTaskIds.value = []
  await loadUploadTasks()
  if (activeTasks.value.length) startTaskPolling()
  else stopTaskPolling()
}

async function changeTaskPage(page) {
  taskPage.value = page
  selectedTaskIds.value = []
  await loadUploadTasks()
  if (activeTasks.value.length) startTaskPolling()
  else stopTaskPolling()
}

async function runTaskAction(action, ids) {
  if (!ids.length) return
  const labels = { retry: '重试', cancel: '取消', delete: '清理' }
  if (action !== 'retry') {
    const description = action === 'delete'
      ? '将删除选中的已结束任务记录，并清理仍保留的暂存文件。'
      : '排队任务会立即取消；处理中任务将在安全检查点停止，已经完成入库的任务仍会保留成功结果。'
    try {
      await ElMessageBox.confirm(description, `${labels[action]}上传任务`, {
        type: 'warning',
        confirmButtonText: `确认${labels[action]}`,
        cancelButtonText: '返回'
      })
    } catch {
      return
    }
  }
  taskActionLoading.value = true
  try {
    const result = await galleryApi.batchUploadTaskAction({ ids, action })
    ElMessage.success(`${labels[action]}完成：处理 ${result.affected} 个，跳过 ${result.skipped} 个`)
    selectedTaskIds.value = []
    await loadUploadTasks({ silent: true })
    if (activeTasks.value.length) startTaskPolling()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || `${labels[action]}任务失败`)
  } finally {
    taskActionLoading.value = false
  }
}

watch(fileList, (files) => {
  syncPreviewItems(files)
}, { deep: true })

watch(totalPreviewPages, (total) => {
  if (previewPage.value > total) {
    previewPage.value = total
  }
})

onMounted(async () => {
  await Promise.all([loadOptions(), loadUploadTasks()])
  if (activeTasks.value.length) startTaskPolling()
})
onBeforeUnmount(() => {
  taskRequestSeq += 1
  cleanupPreviewItems()
  stopTaskPolling()
})
</script>

<template>
  <div class="admin-card">
    <el-form class="image-upload-form" label-position="top">
      <el-form-item class="image-upload-form__section" label="图片文件">
        <div class="upload-picker">
          <input
            ref="nativeFileInput"
            class="upload-picker__input"
            type="file"
            multiple
            :accept="imageUploadAccept"
            @change="handleNativeFiles"
          />
          <el-upload
            v-model:file-list="fileList"
            drag
            multiple
            :auto-upload="false"
            :accept="imageUploadAccept"
            :show-file-list="false"
            @change="handleFileChange"
            @remove="handleFileRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入图片到这里</div>
            <div class="muted" style="margin-top: 6px">支持后缀：{{ imageUploadSupportText }}</div>
            <el-button class="upload-picker__button" type="primary" :icon="UploadFilled" @click.stop.prevent="openNativePicker">
              选择图片
            </el-button>
          </el-upload>
        </div>
      </el-form-item>
      <el-form-item class="image-upload-form__section" label="批量预览">
        <div class="upload-preview-shell">
          <div v-if="previewItems.length" class="upload-preview-toolbar">
            <span class="muted">已选择 {{ totalFiles }} 张</span>
            <el-button v-if="totalFiles" :icon="Delete" @click="clearSelectedFiles">清空</el-button>
          </div>
          <div v-if="previewItems.length" class="upload-preview-grid">
            <div v-for="item in pagedPreviewItems" :key="item.uid" class="upload-preview-card">
              <button class="upload-preview-card__media" type="button" @click="openPreview(item)">
                <img v-if="item.previewUrl" :src="item.previewUrl" :alt="item.name" />
                <div v-else class="upload-preview-card__fallback">
                  <span v-if="item.previewStatus === 'queued'">等待预览</span>
                  <span v-else-if="item.previewStatus === 'loading'">解析中</span>
                  <span v-else>预览失败</span>
                </div>
              </button>
              <el-button class="upload-preview-card__remove" circle :icon="Delete" @click="removePreviewItem(item.uid)" />
              <div class="upload-preview-card__meta">
                <strong>{{ item.name }}</strong>
                <span class="muted">{{ formatBytes(item.size) }} · {{ item.extension }}</span>
                <span v-if="item.previewStatus === 'error'" class="upload-preview-card__error">{{ item.errorMessage }}</span>
              </div>
            </div>
          </div>
          <div v-else class="upload-preview-empty">
            <div class="upload-preview-empty__icon">
              <el-icon><UploadFilled /></el-icon>
            </div>
            <div>
              <strong>等待选择图片</strong>
              <span>预览、重复校验和分页核对会在选择文件后出现在这里。</span>
            </div>
          </div>
          <div v-if="totalFiles > previewPageSize" class="upload-preview-pagination">
            <el-pagination
              v-model:current-page="previewPage"
              background
              layout="prev, pager, next, total"
              :page-size="previewPageSize"
              :total="totalFiles"
            />
          </div>
        </div>
      </el-form-item>
      <el-form-item class="image-upload-form__section" label="上传任务">
        <div v-loading="taskLoading" class="upload-task-panel">
          <div class="upload-task-toolbar">
            <div class="upload-task-toolbar__filters">
              <el-checkbox
                :model-value="allPageTasksSelected"
                :indeterminate="selectedTaskIds.length > 0 && !allPageTasksSelected"
                aria-label="选择本页任务"
                @change="toggleAllPageTasks"
              />
              <el-select v-model="taskStatusFilter" class="upload-task-status-filter" @change="changeTaskStatusFilter">
                <el-option v-for="item in taskStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button circle :icon="Refresh" aria-label="刷新任务" @click="loadUploadTasks()" />
              <span class="muted">共 {{ taskTotal }} 个</span>
            </div>
            <div class="upload-task-toolbar__actions">
              <span v-if="selectedTaskIds.length" class="muted">已选 {{ selectedTaskIds.length }} 个</span>
              <el-button :disabled="!selectedTaskIds.length" :loading="taskActionLoading" @click="runTaskAction('retry', selectedTaskIds)">重试</el-button>
              <el-button :disabled="!selectedTaskIds.length" :loading="taskActionLoading" @click="runTaskAction('cancel', selectedTaskIds)">取消</el-button>
              <el-button type="danger" plain :disabled="!selectedTaskIds.length" :loading="taskActionLoading" @click="runTaskAction('delete', selectedTaskIds)">清理</el-button>
            </div>
          </div>
          <div v-if="taskItems.length" class="upload-task-panel__summary">
            <span>本页活动 {{ activeTasks.length }}</span>
            <span>成功 {{ completedTasks.length }}</span>
            <span>失败 {{ failedTasks.length }}</span>
            <el-button size="small" :icon="ArrowRight" @click="$router.push('/admin/images')">去图片管理</el-button>
          </div>
          <div v-if="taskItems.length" class="upload-task-list">
            <div v-for="task in taskItems" :key="task.id" class="upload-task-item">
              <el-checkbox
                :model-value="selectedTaskIds.includes(task.id)"
                :aria-label="`选择任务 ${task.id}`"
                @change="(selected) => toggleTaskSelection(task.id, selected)"
              />
              <div class="upload-task-item__main">
                <strong>{{ task.original_filename || `任务 ${task.id}` }}</strong>
                <span v-if="task.error_message" class="upload-task-item__error">{{ task.error_message }}</span>
                <span v-else class="muted">
                  {{ task.image_id ? `图片 ID ${task.image_id}` : formatBytes(task.file_size) }}
                  <template v-if="task.duplicate"> · 重复文件</template>
                  <template v-else-if="task.preflight_duplicate"> · 预检重复</template>
                </span>
                <span class="muted">
                  {{ task.attempt_count > 0 ? `尝试 ${task.attempt_count}/${task.max_attempts}` : '历史任务' }}
                  <template v-if="task.next_attempt_at"> · {{ formatTaskTime(task.next_attempt_at) }} 重试</template>
                  <template v-if="task.cancel_requested"> · 正在取消</template>
                </span>
              </div>
              <div class="upload-task-item__actions">
                <el-tag :type="taskStatusType(task.status)">{{ taskStatusLabel(task.status) }}</el-tag>
                <el-button v-if="canRetryTask(task)" size="small" @click="runTaskAction('retry', [task.id])">重试</el-button>
                <el-button v-if="canCancelTask(task)" size="small" @click="runTaskAction('cancel', [task.id])">取消</el-button>
                <el-button v-if="canDeleteTask(task)" size="small" :icon="Delete" circle aria-label="清理任务" @click="runTaskAction('delete', [task.id])" />
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无上传任务" :image-size="64" />
          <el-pagination
            v-if="taskTotal > taskPageSize"
            class="upload-task-pagination"
            background
            layout="prev, pager, next, total"
            :current-page="taskPage"
            :page-size="taskPageSize"
            :total="taskTotal"
            @current-change="changeTaskPage"
          />
        </div>
      </el-form-item>
      <div class="admin-form-workbench">
        <el-form-item label="作品">
          <el-select
            v-model="form.work_ids"
            multiple
            filterable
            remote
            reserve-keyword
            clearable
            style="width: 100%"
            :loading="optionLoading.works"
            :remote-method="loadWorks"
            @visible-change="(visible) => visible && loadWorks()"
          >
            <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select
            v-model="form.character_ids"
            multiple
            filterable
            remote
            reserve-keyword
            clearable
            style="width: 100%"
            :loading="optionLoading.characters"
            :remote-method="loadCharacters"
            @visible-change="(visible) => visible && loadCharacters()"
          >
            <el-option v-for="character in characters" :key="character.id" :label="character.name" :value="character.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="form.artist_name" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="form.source_url" />
        </el-form-item>
        <el-form-item label="分级">
          <el-radio-group v-model="form.rating">
            <el-radio-button label="safe">safe</el-radio-button>
            <el-radio-button label="sensitive">sensitive</el-radio-button>
            <el-radio-button label="hidden">hidden</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item class="upload-public-control" label="公开">
          <div class="upload-public-row">
            <el-switch v-model="form.is_public" />
            <el-button native-type="button" type="primary" :loading="uploading || checkingDuplicates" :disabled="!previewItems.length" @click="submitUpload">
              {{ uploadingLabel }}
            </el-button>
          </div>
        </el-form-item>
      </div>
    </el-form>

    <Teleport to="body">
      <Transition name="upload-preview-lightbox">
        <div v-if="activePreviewItem" class="image-detail-overlay upload-preview-lightbox" @click.self="closePreview">
          <div class="image-detail-overlay__panel upload-preview-lightbox__panel">
            <el-button class="image-detail-overlay__close" circle :icon="Close" aria-label="关闭" @click="closePreview" />
            <div class="upload-preview-lightbox__layout">
              <button
                class="upload-preview-lightbox__nav"
                type="button"
                :disabled="activePreviewIndex <= 0"
                @click="showPreviousPreview"
              >
                <el-icon><ArrowLeft /></el-icon>
              </button>
              <div class="upload-preview-lightbox__stage">
                <img v-if="activePreviewItem.previewUrl" :src="activePreviewItem.previewUrl" :alt="activePreviewItem.name" />
                <div v-else class="upload-preview-lightbox__fallback">
                  <span v-if="activePreviewItem.previewStatus === 'loading'">解析中</span>
                  <span v-else>{{ activePreviewItem.errorMessage || '预览失败' }}</span>
                </div>
              </div>
              <button
                class="upload-preview-lightbox__nav"
                type="button"
                :disabled="activePreviewIndex < 0 || activePreviewIndex >= previewItems.length - 1"
                @click="showNextPreview"
              >
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>
            <div class="upload-preview-lightbox__meta">
              <div>
                <strong>{{ activePreviewItem.name }}</strong>
                <span class="muted">{{ formatBytes(activePreviewItem.size) }} · {{ activePreviewItem.extension }}</span>
              </div>
              <div class="upload-preview-lightbox__actions">
                <el-button type="danger" :icon="Delete" @click="removeActivePreviewItem">删除这张</el-button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
