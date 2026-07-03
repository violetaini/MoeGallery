<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Close, Delete, UploadFilled } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'
import { imageUploadAccept, imageUploadSupportText } from '../../constants/uploadFormats'

const fileList = ref([])
const nativeFileInput = ref(null)
const works = ref([])
const characters = ref([])
const uploading = ref(false)
const checkingDuplicates = ref(false)
const taskItems = ref([])
const taskPollingTimer = ref(null)
const previewItems = ref([])
const previewPage = ref(1)
const previewPageSize = 12
const activePreviewUid = ref(null)
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
const activeTasks = computed(() => taskItems.value.filter((item) => ['queued', 'processing'].includes(item.status)))
const completedTasks = computed(() => taskItems.value.filter((item) => item.status === 'success'))
const failedTasks = computed(() => taskItems.value.filter((item) => item.status === 'failed'))
const duplicateHashConcurrency = 8
const uploadingLabel = computed(() => {
  if (checkingDuplicates.value) return '校验重复中'
  if (uploading.value) return '提交任务中'
  return '开始批量上传'
})

function taskStatusLabel(status) {
  if (status === 'queued') return '排队中'
  if (status === 'processing') return '处理中'
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  return status
}

function taskStatusType(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'processing') return 'warning'
  return 'info'
}

function formatBytes(size) {
  const value = Number(size || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function revokePreview(url) {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url)
  }
}

function cleanupPreviewItems() {
  previewItems.value.forEach((item) => revokePreview(item.previewUrl))
  previewItems.value = []
  activePreviewUid.value = null
  previewPage.value = 1
}

function stopTaskPolling() {
  if (taskPollingTimer.value) {
    window.clearInterval(taskPollingTimer.value)
    taskPollingTimer.value = null
  }
}

async function loadOptions() {
  const [workData, characterData] = await Promise.all([
    galleryApi.works({ page_size: 100 }),
    galleryApi.characters({ page_size: 100 })
  ])
  works.value = workData.items
  characters.value = characterData.items
}

async function createPreview(item) {
  item.previewStatus = 'loading'
  try {
    const blob = await galleryApi.previewUploadImage(item.raw)
    item.previewUrl = URL.createObjectURL(blob)
    item.previewStatus = 'ready'
  } catch (error) {
    item.previewStatus = 'error'
    item.errorMessage = error?.response?.data?.detail || '预览失败'
  }
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
      previewStatus: 'loading',
      errorMessage: ''
    })
    previewItems.value.push(previewItem)
    createPreview(previewItem)
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
  const batchDuplicates = items.filter((item) => item.duplicate_in_batch && !item.duplicate)
  const lines = []
  if (libraryDuplicates.length) {
    lines.push(`图库已有 ${libraryDuplicates.length} 张：`)
    libraryDuplicates.slice(0, 8).forEach((item) => {
      const image = item.existing_image
      const name = image?.original_filename || image?.filename || `图片 ID ${image?.id}`
      lines.push(`- ${item.filename} -> ${name}`)
    })
  }
  if (batchDuplicates.length) {
    lines.push(`本批次内重复 ${batchDuplicates.length} 张：`)
    batchDuplicates.slice(0, 8).forEach((item) => lines.push(`- ${item.filename}`))
  }
  if (libraryDuplicates.length + batchDuplicates.length > 8) {
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
  const duplicateItems = items.filter((item) => item.duplicate || item.duplicate_in_batch)
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

  const duplicateNames = new Set(duplicateItems.map((item) => item.filename))
  const nextFiles = files.filter((file) => !duplicateNames.has(file.name))
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
    taskItems.value = result.items || []
    ElMessage.success(`已提交 ${taskItems.value.length} 个上传任务`)
    clearSelectedFiles()
    startTaskPolling()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '上传失败'
    ElMessage.error(Array.isArray(detail) ? detail.map((item) => item.msg || item).join('；') : detail)
  } finally {
    uploading.value = false
    checkingDuplicates.value = false
  }
}

async function refreshUploadTasks() {
  if (!taskItems.value.length) return
  const ids = taskItems.value.map((item) => item.id).join(',')
  try {
    const data = await galleryApi.uploadTasks({ ids })
    taskItems.value = data.items || []
    if (!activeTasks.value.length) {
      stopTaskPolling()
      const duplicateCount = taskItems.value.filter((item) => item.duplicate).length
      if (failedTasks.value.length) {
        ElMessage.warning(`上传任务完成：成功 ${completedTasks.value.length} 个，失败 ${failedTasks.value.length} 个，重复 ${duplicateCount} 个`)
      } else {
        ElMessage.success(`上传任务完成：成功 ${completedTasks.value.length} 个，重复 ${duplicateCount} 个`)
      }
    }
  } catch (error) {
    stopTaskPolling()
    ElMessage.error(error?.response?.data?.detail || '刷新上传任务失败')
  }
}

function startTaskPolling() {
  stopTaskPolling()
  refreshUploadTasks()
  taskPollingTimer.value = window.setInterval(refreshUploadTasks, 1500)
}

watch(fileList, (files) => {
  syncPreviewItems(files)
}, { deep: true })

watch(totalPreviewPages, (total) => {
  if (previewPage.value > total) {
    previewPage.value = total
  }
})

onMounted(loadOptions)
onBeforeUnmount(() => {
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
                  <span v-if="item.previewStatus === 'loading'">解析中</span>
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
      <el-form-item v-if="taskItems.length" class="image-upload-form__section" label="任务状态">
        <div class="upload-task-panel">
          <div class="upload-task-panel__summary">
            <span>处理中 {{ activeTasks.length }}</span>
            <span>成功 {{ completedTasks.length }}</span>
            <span>失败 {{ failedTasks.length }}</span>
            <el-button size="small" :icon="ArrowRight" @click="$router.push('/admin/images')">去图片管理</el-button>
          </div>
          <div class="upload-task-list">
            <div v-for="task in taskItems" :key="task.id" class="upload-task-item">
              <div class="upload-task-item__main">
                <strong>{{ task.original_filename || `任务 ${task.id}` }}</strong>
                <span v-if="task.error_message" class="upload-task-item__error">{{ task.error_message }}</span>
                <span v-else class="muted">
                  {{ task.image_id ? `图片 ID ${task.image_id}` : formatBytes(task.file_size) }}
                  <template v-if="task.duplicate"> · 重复文件</template>
                </span>
              </div>
              <el-tag :type="taskStatusType(task.status)">{{ taskStatusLabel(task.status) }}</el-tag>
            </div>
          </div>
        </div>
      </el-form-item>
      <div class="admin-form-workbench">
        <el-form-item label="作品">
          <el-select v-model="form.work_ids" multiple filterable clearable style="width: 100%">
            <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.character_ids" multiple filterable clearable style="width: 100%">
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
