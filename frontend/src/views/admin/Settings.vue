<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Delete, Edit, Loading, Plus, Refresh } from '@element-plus/icons-vue'
import { adminAvatarUrlFromImage, clearAuthSession, mediaUrl, setAuthSession } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import { orientationLabel, orientationOptions } from '../../constants/orientations'
import { imageUploadAccept } from '../../constants/uploadFormats'
import {
  getImageManageViewMode,
  imageManageViewModes,
  normalizeImageManageViewMode,
  setImageManageViewMode
} from '../../utils/adminPreferences'

const imageManageViewMode = ref(getImageManageViewMode())
const router = useRouter()
const uploadWorkerCount = ref(12)
const uploadWorkerLimit = ref(96)
const databaseConcurrencyProfile = ref('generic')
const uploadClaimBatchSize = ref(1)
const uploadTaskMaxAttempts = ref(3)
const uploadFailedRetentionDays = ref(7)
const randomApiDesktopOrientation = ref('landscape')
const randomApiMobileOrientation = ref('portrait')
const randomApiDefaultRating = ref('safe')
const randomApiDefaultVariant = ref('preview')
const githubProxyUrl = ref('')
const cdnWarmEnabled = ref(false)
const cdnWarmBaseUrl = ref('')
const cdnWarmStatus = ref(null)
const cdnWarmLoading = ref(false)
const cdnWarmSaving = ref(false)
const cdnWarmSeeding = ref(false)
const operationsApiKeys = ref([])
const apiKeyScopes = ref([])
const visibleApiKeyIds = ref(new Set())
const resettingApiKeys = ref(false)
const apiKeyDialogOpen = ref(false)
const apiKeySaving = ref(false)
const editingApiKeyId = ref(null)
const rotatingApiKeyId = ref(null)
const apiKeyForm = ref({ name: '', scopes: ['library:read'], expires_at: null })
const adminUsername = ref('')
const adminPassword = ref('')
const adminPasswordChangeRequired = ref(false)
const adminAvatarImage = ref(null)
const adminAvatarImageId = ref(null)
const avatarUploading = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const healthLoading = ref(false)
const rotatingSecret = ref(false)
const health = ref(null)
const healthError = ref('')
const homeSlideshowImageIds = ref([])
const homeSlideshowImages = ref([])
const homeSlideshowImageOptions = ref([])
const homeSlideshowImageLoading = ref(false)
const homeSlideshowPickerOpen = ref(false)
const homeSlideshowPickerImages = ref([])
const homeSlideshowPickerTotal = ref(0)
const homeSlideshowPickerPage = ref(1)
const homeSlideshowPickerPageSize = 24
const homeSlideshowImageQuery = ref('')
const homeSlideshowWorkId = ref()
const homeSlideshowCharacterId = ref()
const homeSlideshowOrientation = ref('landscape')
const homeSlideshowWorkOptions = ref([])
const homeSlideshowCharacterOptions = ref([])
const homeSlideshowWorkLoading = ref(false)
const homeSlideshowCharacterLoading = ref(false)
let homeSlideshowImageSearchSeq = 0
let homeSlideshowWorkSearchSeq = 0
let homeSlideshowCharacterSearchSeq = 0
const heroBackgroundItems = ref([
  {
    key: 'home',
    label: '图片库',
    hint: '前台首页图片库首卡背景。',
    fallback: '/hero/gallery-bg.jpg',
    imageIdField: 'home_hero_image_id',
    imageField: 'home_hero_image',
    clearField: 'clear_home_hero_image',
    imageId: null,
    image: null,
    uploading: false
  },
  {
    key: 'works',
    label: '作品',
    hint: '前台作品索引首卡背景。',
    fallback: '/hero/works-bg.jpg',
    imageIdField: 'works_hero_image_id',
    imageField: 'works_hero_image',
    clearField: 'clear_works_hero_image',
    imageId: null,
    image: null,
    uploading: false
  },
  {
    key: 'characters',
    label: '角色',
    hint: '前台角色索引首卡背景。',
    fallback: '/hero/characters-bg.png',
    imageIdField: 'characters_hero_image_id',
    imageField: 'characters_hero_image',
    clearField: 'clear_characters_hero_image',
    imageId: null,
    image: null,
    uploading: false
  },
  {
    key: 'ratings',
    label: '分级',
    hint: '前台分级页首卡背景。',
    fallback: '/hero/ratings-bg.png',
    imageIdField: 'ratings_hero_image_id',
    imageField: 'ratings_hero_image',
    clearField: 'clear_ratings_hero_image',
    imageId: null,
    image: null,
    uploading: false
  }
])

const randomApiOrientationOptions = [
  ...orientationOptions,
  { value: 'any', label: '不限方向' }
]
const randomApiRatingOptions = [
  { value: 'safe', label: '仅安全' },
  { value: 'sensitive', label: '仅敏感' },
  { value: 'any', label: '安全与敏感' }
]
const randomApiVariantOptions = [
  { value: 'preview', label: '预览图' },
  { value: 'original', label: '原图' },
  { value: 'thumbnail', label: '缩略图' }
]

const adminAvatarUrl = computed(() => adminAvatarUrlFromImage(adminAvatarImage.value) || '/avatar.webp')
const uploadWorkerHint = computed(() => {
  if (databaseConcurrencyProfile.value === 'sqlite_conservative') {
    return `SQLite 单写入模式，当前最多 ${uploadWorkerLimit.value} 个 worker。`
  }
  if (databaseConcurrencyProfile.value === 'mysql_high_throughput') {
    return `MySQL 并行领取任务，当前最多 ${uploadWorkerLimit.value} 个 worker。`
  }
  return `当前数据库最多允许 ${uploadWorkerLimit.value} 个 worker。`
})
const cdnWarmProgress = computed(() => Math.max(0, Math.min(100, Number(cdnWarmStatus.value?.coverage_percentage ?? 0))))
const selectedHomeSlideshowImages = computed(() => {
  const imageById = new Map()
  ;[...homeSlideshowImages.value, ...homeSlideshowImageOptions.value, ...homeSlideshowPickerImages.value].forEach((image) => {
    if (image?.id) imageById.set(image.id, image)
  })
  return homeSlideshowImageIds.value.map((id) => imageById.get(id)).filter(Boolean)
})
const imageFileCapacity = computed(() => {
  if (!health.value) return healthLoading.value ? '正在检查' : '未加载'
  const original = storageStats('original')
  const preview = storageStats('preview')
  const thumbnail = storageStats('thumbnail')
  return formatBytes(
    Number(original.size_bytes || 0) +
    Number(preview.size_bytes || 0) +
    Number(thumbnail.size_bytes || 0)
  )
})

const healthCards = computed(() => {
  const data = health.value
  if (!data) return []
  const application = data.application || {}
  const latestRelease = application.latest_release || {}
  const migration = application.migration || {}
  const original = storageStats('original')
  const preview = storageStats('preview')
  const thumbnail = storageStats('thumbnail')
  const consistency = data.storage?.consistency || {}
  const ffmpeg = data.capabilities?.ffmpeg || {}
  const jxr = data.capabilities?.jxr_decode || {}
  const hdr = data.capabilities?.hdr_avif_metadata_patch || {}
  const authSecret = data.security?.auth_secret || {}
  const mediaDelivery = data.media_delivery || {}
  const database = data.database || {}
  const databaseConcurrency = database.concurrency || {}
  const databaseDetail =
    database.dialect === 'sqlite'
      ? `SQLite · ${databaseConcurrency.journal_mode === 'wal' ? 'WAL' : '非 WAL'} · 忙等 ${Math.round(Number(databaseConcurrency.busy_timeout_ms || 0) / 1000)} 秒`
      : `${database.dialect || 'Database'} · 连接 ${databaseConcurrency.pool?.checked_out ?? 0}/${databaseConcurrency.pool_capacity ?? databaseConcurrency.pool_size ?? '-'}`
  const fileHealth = formatImageFileHealth(consistency, original, preview, thumbnail)
  const missingFileDirs = [
    ['原图', original.exists],
    ['预览图', preview.exists],
    ['缩略图', thumbnail.exists]
  ]
    .filter(([, exists]) => !exists)
    .map(([label]) => label)
  const fileHealthBaseDetail = missingFileDirs.length
    ? `${missingFileDirs.join('、')}目录缺失`
    : fileHealth.message
  const mediaDeliveryMode = mediaDelivery.accel_redirect_enabled ? 'Nginx 发送' : '应用发送'
  const fileHealthDetail = `${fileHealthBaseDetail} · ${mediaDeliveryMode} · CDN ${mediaDelivery.public_shared_cache_seconds ?? 300} 秒`
  const filesReady = missingFileDirs.length === 0 && fileHealth.complete
  const migrationReady = migration.up_to_date !== false
  const versionDetail = !migrationReady
    ? '数据库待迁移'
    : application.update_available
      ? `可更新至 ${latestRelease.version || '新版本'}`
      : latestRelease.available
        ? '已是最新'
        : '更新检查失败'
  const imageCapabilityReady = jxr.available && hdr.available
  return [
    {
      key: 'version',
      label: '程序版本',
      value: application.current_version || '未知',
      detail: versionDetail,
      tone: application.update_available || !migrationReady ? 'warning' : 'ok'
    },
    {
      key: 'database',
      label: '数据库',
      value: database.exists ? '正常' : '异常',
      detail: databaseDetail,
      tone: database.exists ? 'ok' : 'danger'
    },
    {
      key: 'storage',
      label: '图片文件',
      value: filesReady ? '完整' : '需检查',
      detail: fileHealthDetail,
      tone: filesReady ? 'ok' : 'warning'
    },
    {
      key: 'upload',
      label: '上传队列',
      value: `${data.upload_queue?.worker_alive ?? 0}/${data.upload_queue?.worker_target ?? data.upload_queue?.worker_count ?? uploadWorkerCount.value} worker`,
      detail: `排队 ${data.upload_queue?.queued ?? 0} · 处理中 ${data.upload_queue?.processing ?? 0} · 上限 ${data.upload_queue?.worker_limit ?? uploadWorkerLimit.value}`,
      tone: (data.upload_queue?.failed ?? 0) > 0 ? 'warning' : 'info'
    },
    {
      key: 'ffmpeg',
      label: 'ffmpeg',
      value: ffmpeg.available ? '可用' : '不可用',
      detail: ffmpeg.available ? `AVIF 编码：${ffmpeg.avif_encoder ? '支持' : '未确认'}` : '未检测到可用命令',
      tone: ffmpeg.available ? 'ok' : 'danger'
    },
    {
      key: 'image-capabilities',
      label: '图像能力',
      value: imageCapabilityReady ? '完整' : '需检查',
      detail: `JXR ${jxr.available ? '可用' : '缺失'} · HDR ${hdr.available ? '可用' : '缺失'}`,
      tone: imageCapabilityReady ? 'ok' : 'warning'
    },
    {
      key: 'auth-secret',
      label: '登录密钥',
      value: authSecret.strong ? '已保护' : '需处理',
      detail: authSecret.configured ? '持久化强密钥' : '临时密钥',
      tone: authSecret.strong ? 'ok' : 'danger'
    }
  ]
})

function formatBytes(value) {
  const size = Number(value || 0)
  if (size >= 1024 * 1024 * 1024) return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function formatImageFileHealth(consistency, original, preview, thumbnail) {
  const expected = Number(consistency?.image_records || 0)
  const expectedPreview = Number(consistency?.expected?.preview ?? expected)
  const sections = [
    ['原图', Number(original.file_count || 0), expected],
    ['HDR预览', Number(preview.file_count || 0), expectedPreview],
    ['缩略图', Number(thumbnail.file_count || 0), expected]
  ]
  const issues = sections
    .map(([label, count, expectedCount]) => {
      const diff = count - expectedCount
      if (diff < 0) return `${label}缺失 ${Math.abs(diff)} 个`
      if (diff > 0 && label !== 'HDR预览') return `${label}多出 ${diff} 个`
      return ''
    })
    .filter(Boolean)
  const legacyPreviews = Math.max(
    Number(consistency?.legacy_preview_files || 0),
    Number(consistency?.legacy_preview_references || 0)
  )
  if (legacyPreviews > 0) {
    issues.push(`待清理旧预览 ${legacyPreviews} 个`)
  }
  if (!issues.length) {
    return { complete: true, message: `${expected} 张图片，文件完整` }
  }
  return { complete: false, message: issues.join('；') }
}

function storageStats(name) {
  return health.value?.storage?.[name] || {
    path: '未返回存储路径',
    file_count: 0,
    size_bytes: 0
  }
}

function syncAccount(data) {
  adminUsername.value = data.admin_username || ''
  adminPasswordChangeRequired.value = Boolean(data.admin_password_change_required)
  adminAvatarImageId.value = data.admin_avatar_image_id || null
  adminAvatarImage.value = data.admin_avatar_image || null
  syncHomeSlideshowImages(data)
  syncHeroBackgrounds(data)
  setAuthSession({ username: adminUsername.value, avatar_image: adminAvatarImage.value })
}

function syncOperationsApiKeys(data) {
  operationsApiKeys.value = Array.isArray(data.operations_api_keys) ? data.operations_api_keys : []
  apiKeyScopes.value = Array.isArray(data.api_key_scopes) ? data.api_key_scopes : apiKeyScopes.value
  const configuredIds = new Set(operationsApiKeys.value.map((item) => item.id))
  visibleApiKeyIds.value = new Set([...visibleApiKeyIds.value].filter((id) => configuredIds.has(id)))
}

function isApiKeyVisible(id) {
  return visibleApiKeyIds.value.has(id)
}

function setApiKeyVisible(id, visible) {
  const next = new Set(visibleApiKeyIds.value)
  if (visible) next.add(id)
  else next.delete(id)
  visibleApiKeyIds.value = next
}

function toggleApiKeyVisible(id) {
  setApiKeyVisible(id, !isApiKeyVisible(id))
}

function apiKeyScopeLabel(scope) {
  return apiKeyScopes.value.find((item) => item.value === scope)?.label || scope
}

function formatApiKeyTime(value, fallback = '从不过期') {
  if (!value) return fallback
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString('zh-CN', { hour12: false })
}

function openCreateApiKey() {
  editingApiKeyId.value = null
  apiKeyForm.value = { name: '', scopes: ['library:read'], expires_at: null }
  apiKeyDialogOpen.value = true
}

function openEditApiKey(item) {
  editingApiKeyId.value = item.id
  apiKeyForm.value = {
    name: item.name,
    scopes: [...item.scopes],
    expires_at: item.expires_at ? new Date(item.expires_at) : null
  }
  apiKeyDialogOpen.value = true
}

function selectAllApiKeyScopes() {
  apiKeyForm.value.scopes = apiKeyScopes.value.map((item) => item.value)
}

async function saveApiKey() {
  if (!apiKeyForm.value.name.trim()) {
    ElMessage.warning('请输入 Key 名称')
    return
  }
  if (!apiKeyForm.value.scopes.length) {
    ElMessage.warning('请至少选择一项权限')
    return
  }
  apiKeySaving.value = true
  const payload = {
    name: apiKeyForm.value.name.trim(),
    scopes: apiKeyForm.value.scopes,
    expires_at: apiKeyForm.value.expires_at ? apiKeyForm.value.expires_at.toISOString() : null
  }
  try {
    const item = editingApiKeyId.value
      ? await galleryApi.updateApiKey(editingApiKeyId.value, payload)
      : await galleryApi.createApiKey(payload)
    const index = operationsApiKeys.value.findIndex((key) => key.id === item.id)
    if (index >= 0) operationsApiKeys.value.splice(index, 1, item)
    else operationsApiKeys.value.push(item)
    setApiKeyVisible(item.id, true)
    apiKeyDialogOpen.value = false
    ElMessage.success(editingApiKeyId.value ? 'API Key 已更新' : 'API Key 已创建')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存 API Key 失败')
  } finally {
    apiKeySaving.value = false
  }
}

async function revokeOperationsApiKey(item) {
  const confirmed = await ElMessageBox.confirm(
    `撤销后“${item.name}”会立即失效，使用它的任务将无法继续调用 API。`,
    '撤销 API Key',
    {
      type: 'warning',
      confirmButtonText: '确认撤销',
      cancelButtonText: '取消',
      closeOnClickModal: false
    }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  try {
    await galleryApi.revokeApiKey(item.id)
    operationsApiKeys.value = operationsApiKeys.value.filter((key) => key.id !== item.id)
    setApiKeyVisible(item.id, false)
    ElMessage.success('API Key 已撤销')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '撤销 API Key 失败')
  }
}

async function rotateOperationsApiKey(item) {
  const confirmed = await ElMessageBox.confirm(
    `刷新后“${item.name}”的旧 Key 会立即失效，名称、权限和有效期保持不变。确认继续？`,
    '刷新 API Key',
    {
      type: 'warning',
      confirmButtonText: '确认刷新',
      cancelButtonText: '取消',
      closeOnClickModal: false
    }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  rotatingApiKeyId.value = item.id
  try {
    const refreshed = await galleryApi.rotateApiKey(item.id)
    const index = operationsApiKeys.value.findIndex((key) => key.id === item.id)
    if (index >= 0) operationsApiKeys.value.splice(index, 1, refreshed)
    setApiKeyVisible(refreshed.id, true)
    ElMessage.success('API Key 已刷新，请及时更新使用旧 Key 的任务')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '刷新 API Key 失败')
  } finally {
    rotatingApiKeyId.value = null
  }
}

function syncRandomApiSettings(data) {
  randomApiDesktopOrientation.value = data.random_api_desktop_orientation || 'landscape'
  randomApiMobileOrientation.value = data.random_api_mobile_orientation || 'portrait'
  randomApiDefaultRating.value = data.random_api_default_rating || 'safe'
  randomApiDefaultVariant.value = data.random_api_default_variant || 'preview'
}

function syncCdnWarmStatus(data) {
  cdnWarmStatus.value = data || null
  const config = data?.config || data || {}
  cdnWarmEnabled.value = Boolean(config.enabled)
  cdnWarmBaseUrl.value = config.base_url || ''
}

function cdnProviderLabel(value) {
  return {
    esa: 'ESA',
    edgeone: 'EdgeOne',
    cloudflare: 'Cloudflare',
    direct: '直连源站',
    unknown: '待探测'
  }[value] || value || '待探测'
}

function cdnCacheStatusType(value) {
  if (['HIT', 'REVALIDATED', 'REFRESHHIT'].includes(String(value || '').toUpperCase())) return 'success'
  if (['MISS', 'UNKNOWN'].includes(String(value || '').toUpperCase())) return 'warning'
  return 'info'
}

function syncHomeSlideshowImages(data) {
  homeSlideshowImageIds.value = Array.isArray(data.home_slideshow_image_ids) ? data.home_slideshow_image_ids : []
  homeSlideshowImages.value = Array.isArray(data.home_slideshow_images) ? data.home_slideshow_images : []
  mergeHomeSlideshowImageOptions(homeSlideshowImages.value)
}

function syncHeroBackgrounds(data) {
  heroBackgroundItems.value.forEach((item) => {
    item.imageId = data[item.imageIdField] || null
    item.image = data[item.imageField] || null
  })
}

function heroBackgroundUrl(item) {
  return mediaUrl(item.image, 'preview') || item.fallback
}

function imageDisplayName(image) {
  return image?.original_filename || image?.filename || `图片 ${image?.id || ''}`
}

function imageThumbnailUrl(image) {
  return mediaUrl(image, 'thumbnail')
}

function workOptionLabel(work) {
  return work?.original_name ? `${work.name} / ${work.original_name}` : work?.name || `作品 ${work?.id || ''}`
}

function characterOptionLabel(character) {
  return character?.original_name
    ? `${character.name} / ${character.original_name}`
    : character?.name || `角色 ${character?.id || ''}`
}

function mergeHomeSlideshowImageOptions(images = []) {
  const imageById = new Map()
  ;[...homeSlideshowImageOptions.value, ...homeSlideshowImages.value, ...images].forEach((image) => {
    if (image?.id) imageById.set(image.id, image)
  })
  homeSlideshowImageOptions.value = Array.from(imageById.values())
}

function syncSelectedHomeSlideshowImages() {
  const imageById = new Map()
  ;[...homeSlideshowImages.value, ...homeSlideshowImageOptions.value].forEach((image) => {
    if (image?.id) imageById.set(image.id, image)
  })
  homeSlideshowImages.value = homeSlideshowImageIds.value.map((id) => imageById.get(id)).filter(Boolean)
  mergeHomeSlideshowImageOptions(homeSlideshowImages.value)
}

async function loadHomeSlideshowImageOptions(page = homeSlideshowPickerPage.value) {
  const seq = ++homeSlideshowImageSearchSeq
  homeSlideshowImageLoading.value = true
  try {
    homeSlideshowPickerPage.value = page
    const params = {
      page,
      page_size: homeSlideshowPickerPageSize,
      sort: 'latest'
    }
    const q = homeSlideshowImageQuery.value.trim()
    if (q) params.q = q
    if (homeSlideshowWorkId.value) params.work_id = homeSlideshowWorkId.value
    if (homeSlideshowCharacterId.value) params.character_id = homeSlideshowCharacterId.value
    if (homeSlideshowOrientation.value) params.orientation = homeSlideshowOrientation.value
    const data = await galleryApi.images(params)
    if (seq === homeSlideshowImageSearchSeq) {
      homeSlideshowPickerImages.value = data.items || []
      homeSlideshowPickerTotal.value = Number(data.total || 0)
      mergeHomeSlideshowImageOptions(homeSlideshowPickerImages.value)
    }
  } catch (error) {
    if (seq === homeSlideshowImageSearchSeq) {
      ElMessage.error(error?.response?.data?.detail || '加载首页放映图片失败')
    }
  } finally {
    if (seq === homeSlideshowImageSearchSeq) {
      homeSlideshowImageLoading.value = false
    }
  }
}

async function loadHomeSlideshowWorkOptions(query = '') {
  const seq = ++homeSlideshowWorkSearchSeq
  homeSlideshowWorkLoading.value = true
  try {
    const params = { page_size: 50 }
    const q = query?.trim()
    if (q) params.q = q
    const data = await galleryApi.works(params)
    if (seq === homeSlideshowWorkSearchSeq) {
      homeSlideshowWorkOptions.value = data.items || []
    }
  } catch (error) {
    if (seq === homeSlideshowWorkSearchSeq) {
      ElMessage.error(error?.response?.data?.detail || '加载作品筛选失败')
    }
  } finally {
    if (seq === homeSlideshowWorkSearchSeq) {
      homeSlideshowWorkLoading.value = false
    }
  }
}

async function loadHomeSlideshowCharacterOptions(query = '') {
  const seq = ++homeSlideshowCharacterSearchSeq
  homeSlideshowCharacterLoading.value = true
  try {
    const params = { page_size: 50 }
    const q = query?.trim()
    if (q) params.q = q
    if (homeSlideshowWorkId.value) params.work_id = homeSlideshowWorkId.value
    const data = await galleryApi.characters(params)
    if (seq === homeSlideshowCharacterSearchSeq) {
      homeSlideshowCharacterOptions.value = data.items || []
    }
  } catch (error) {
    if (seq === homeSlideshowCharacterSearchSeq) {
      ElMessage.error(error?.response?.data?.detail || '加载角色筛选失败')
    }
  } finally {
    if (seq === homeSlideshowCharacterSearchSeq) {
      homeSlideshowCharacterLoading.value = false
    }
  }
}

function openHomeSlideshowPicker() {
  homeSlideshowPickerOpen.value = true
  loadHomeSlideshowWorkOptions()
  loadHomeSlideshowCharacterOptions()
  loadHomeSlideshowImageOptions(1)
}

function searchHomeSlideshowImages() {
  loadHomeSlideshowImageOptions(1)
}

function handleHomeSlideshowWorkFilterChange() {
  homeSlideshowCharacterId.value = undefined
  loadHomeSlideshowCharacterOptions()
  loadHomeSlideshowImageOptions(1)
}

function handleHomeSlideshowCharacterFilterChange() {
  loadHomeSlideshowImageOptions(1)
}

function resetHomeSlideshowPickerFilters() {
  homeSlideshowImageQuery.value = ''
  homeSlideshowWorkId.value = undefined
  homeSlideshowCharacterId.value = undefined
  homeSlideshowOrientation.value = 'landscape'
  loadHomeSlideshowWorkOptions()
  loadHomeSlideshowCharacterOptions()
  loadHomeSlideshowImageOptions(1)
}

function handleHomeSlideshowPickerPage(page) {
  loadHomeSlideshowImageOptions(page)
}

function isHomeSlideshowImageSelected(imageId) {
  return homeSlideshowImageIds.value.includes(imageId)
}

function toggleHomeSlideshowImage(image) {
  if (!image?.id) return
  if (isHomeSlideshowImageSelected(image.id)) {
    removeHomeSlideshowImage(image.id)
    return
  }
  if (homeSlideshowImageIds.value.length >= 24) {
    ElMessage.warning('首页放映图片最多选择 24 张')
    return
  }
  mergeHomeSlideshowImageOptions([image])
  homeSlideshowImageIds.value = [...homeSlideshowImageIds.value, image.id]
  syncSelectedHomeSlideshowImages()
}

function removeHomeSlideshowImage(imageId) {
  homeSlideshowImageIds.value = homeSlideshowImageIds.value.filter((id) => id !== imageId)
  syncSelectedHomeSlideshowImages()
}

function moveHomeSlideshowImage(index, offset) {
  const nextIndex = index + offset
  if (nextIndex < 0 || nextIndex >= homeSlideshowImageIds.value.length) return
  const ids = [...homeSlideshowImageIds.value]
  const [imageId] = ids.splice(index, 1)
  ids.splice(nextIndex, 0, imageId)
  homeSlideshowImageIds.value = ids
  syncSelectedHomeSlideshowImages()
}

function clearHomeSlideshowImages() {
  homeSlideshowImageIds.value = []
  homeSlideshowImages.value = []
}

async function loadAdminSettings() {
  settingsLoading.value = true
  try {
    const data = await galleryApi.settings()
    imageManageViewMode.value = normalizeImageManageViewMode(data.image_manage_view_mode)
    uploadWorkerCount.value = data.upload_worker_count || 12
    uploadWorkerLimit.value = data.upload_worker_limit || 96
    databaseConcurrencyProfile.value = data.database_concurrency_profile || 'generic'
    uploadClaimBatchSize.value = data.upload_claim_batch_size || 1
    uploadTaskMaxAttempts.value = data.upload_task_max_attempts || 3
    uploadFailedRetentionDays.value = data.upload_failed_retention_days || 7
    githubProxyUrl.value = data.github_proxy_url || ''
    syncOperationsApiKeys(data)
    syncRandomApiSettings(data)
    syncAccount(data)
    setImageManageViewMode(imageManageViewMode.value)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载设置失败')
  } finally {
    settingsLoading.value = false
  }
}

async function loadCdnWarmStatus() {
  cdnWarmLoading.value = true
  try {
    syncCdnWarmStatus(await galleryApi.cdnWarmStatus())
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载 CDN 预热状态失败')
  } finally {
    cdnWarmLoading.value = false
  }
}

async function saveCdnWarmConfig() {
  cdnWarmSaving.value = true
  try {
    const config = await galleryApi.updateCdnWarmConfig({
      enabled: cdnWarmEnabled.value,
      base_url: cdnWarmBaseUrl.value.trim(),
      auto_new_uploads: cdnWarmEnabled.value
    })
    syncCdnWarmStatus({ ...(cdnWarmStatus.value || {}), config })
    ElMessage.success(config.enabled ? 'CDN 预热已启用并完成域名探测' : 'CDN 预热已停用')
    await loadCdnWarmStatus()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存 CDN 预热设置失败')
  } finally {
    cdnWarmSaving.value = false
  }
}

async function probeCdnWarm() {
  cdnWarmLoading.value = true
  try {
    const result = await galleryApi.probeCdnWarm()
    ElMessage[result.detected ? 'success' : 'warning'](
      `${cdnProviderLabel(result.provider)} · ${result.cache_status || 'UNKNOWN'} · ${result.message}`
    )
    await loadCdnWarmStatus()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || 'CDN 探测失败')
  } finally {
    cdnWarmLoading.value = false
  }
}

async function seedCdnWarmThumbnails() {
  const confirmed = await ElMessageBox.confirm(
    '会按队列分批访问所有公开图片的缩略图 URL，触发 CDN 缓存；不会预热全量原图。确认继续？',
    '补齐 CDN 缩略图预热',
    { type: 'warning', confirmButtonText: '开始预热', cancelButtonText: '取消', closeOnClickModal: false }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  cdnWarmSeeding.value = true
  try {
    const result = await galleryApi.seedCdnWarmThumbnails()
    ElMessage.success(`预热队列：新增 ${result.queued}，重试 ${result.retried}，已有 ${result.existing}`)
    await loadCdnWarmStatus()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '创建 CDN 预热任务失败')
  } finally {
    cdnWarmSeeding.value = false
  }
}

async function saveAdminPreferences() {
  if (!adminUsername.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (adminPasswordChangeRequired.value && !adminPassword.value) {
    ElMessage.warning('请先设置新的管理员密码')
    return
  }
  settingsSaving.value = true
  try {
    const payload = {
      admin_username: adminUsername.value.trim(),
      admin_avatar_image_id: adminAvatarImageId.value || undefined,
      home_slideshow_image_ids: homeSlideshowImageIds.value,
      image_manage_view_mode: normalizeImageManageViewMode(imageManageViewMode.value),
      random_api_desktop_orientation: randomApiDesktopOrientation.value,
      random_api_mobile_orientation: randomApiMobileOrientation.value,
      random_api_default_rating: randomApiDefaultRating.value,
      random_api_default_variant: randomApiDefaultVariant.value,
      upload_worker_count: uploadWorkerCount.value,
      upload_claim_batch_size: uploadClaimBatchSize.value,
      upload_task_max_attempts: uploadTaskMaxAttempts.value,
      upload_failed_retention_days: uploadFailedRetentionDays.value,
      github_proxy_url: githubProxyUrl.value.trim()
    }
    heroBackgroundItems.value.forEach((item) => {
      if (item.imageId) payload[item.imageIdField] = item.imageId
    })
    if (adminPassword.value) payload.admin_password = adminPassword.value
    const data = await galleryApi.updateSettings(payload)
    adminPassword.value = ''
    imageManageViewMode.value = normalizeImageManageViewMode(data.image_manage_view_mode)
    uploadWorkerCount.value = data.upload_worker_count
    uploadWorkerLimit.value = data.upload_worker_limit || 96
    databaseConcurrencyProfile.value = data.database_concurrency_profile || 'generic'
    uploadClaimBatchSize.value = data.upload_claim_batch_size
    uploadTaskMaxAttempts.value = data.upload_task_max_attempts
    uploadFailedRetentionDays.value = data.upload_failed_retention_days
    githubProxyUrl.value = data.github_proxy_url || ''
    syncOperationsApiKeys(data)
    syncRandomApiSettings(data)
    syncAccount(data)
    setImageManageViewMode(imageManageViewMode.value)
    ElMessage.success('后台偏好已保存')
    await loadSystemHealth()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存后台偏好失败')
    await loadAdminSettings()
  } finally {
    settingsSaving.value = false
  }
}

async function uploadAdminAvatar(file) {
  avatarUploading.value = true
  try {
    const data = new FormData()
    data.append('files', file)
    data.append('rating', 'safe')
    data.append('is_public', 'true')
    const result = await galleryApi.uploadImages(data)
    const image = result.items?.[0]?.image
    if (!image) throw new Error('上传头像失败')
    adminAvatarImage.value = image
    adminAvatarImageId.value = image.id
    const saved = await galleryApi.updateSettings({ admin_avatar_image_id: image.id })
    syncAccount(saved)
    ElMessage.success('头像已更新')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '上传头像失败')
  } finally {
    avatarUploading.value = false
  }
  return false
}

async function uploadHeroBackground(item, file) {
  item.uploading = true
  try {
    const data = new FormData()
    data.append('files', file)
    data.append('rating', 'safe')
    data.append('is_public', 'true')
    const result = await galleryApi.uploadImages(data)
    const image = result.items?.[0]?.image
    if (!image) throw new Error('上传背景失败')
    item.image = image
    item.imageId = image.id
    const saved = await galleryApi.updateSettings({ [item.imageIdField]: image.id })
    syncHeroBackgrounds(saved)
    ElMessage.success(`${item.label}背景已更新`)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '上传背景失败')
  } finally {
    item.uploading = false
  }
  return false
}

async function resetHeroBackground(item) {
  try {
    const saved = await galleryApi.updateSettings({ [item.clearField]: true })
    syncHeroBackgrounds(saved)
    ElMessage.success(`已恢复默认${item.label}背景`)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '恢复默认背景失败')
  }
}

async function loadSystemHealth(forceRefresh = false) {
  healthLoading.value = true
  healthError.value = ''
  try {
    health.value = await galleryApi.systemHealth(forceRefresh ? { refresh: true } : {})
  } catch (error) {
    healthError.value = error?.response?.data?.detail || error?.message || '加载系统健康检查失败'
    ElMessage.error(healthError.value)
  } finally {
    healthLoading.value = false
  }
}

async function rotateLoginSecret() {
  const confirmed = await ElMessageBox.confirm(
    '轮换后所有后台会话都会立即失效，需要重新登录。确认继续？',
    '轮换登录密钥',
    {
      type: 'warning',
      confirmButtonText: '确认轮换',
      cancelButtonText: '取消',
      closeOnClickModal: false
    }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  rotatingSecret.value = true
  try {
    const result = await galleryApi.rotateAuthSecret()
    clearAuthSession()
    ElMessage.success(`登录密钥已轮换，已吊销 ${result.revoked_sessions ?? 0} 个会话`)
    await router.replace('/login')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '轮换登录密钥失败')
  } finally {
    rotatingSecret.value = false
  }
}

async function copyApiKey(key) {
  let copied = false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(key)
      copied = true
    }
  } catch {
    copied = false
  }
  if (!copied) {
    const textarea = document.createElement('textarea')
    textarea.value = key
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    copied = document.execCommand('copy')
    textarea.remove()
  }
  if (copied) {
    ElMessage.success('API Key 已复制')
  } else {
    ElMessage.error('复制失败，请手动选中复制')
  }
}

async function resetOperationsApiKeys() {
  const confirmed = await ElMessageBox.confirm(
    '重置后旧 API Key 会立即失效，依赖旧 Key 的脚本、监控和自动化任务都需要同步更新。确认继续？',
    '重置 API Key',
    {
      type: 'warning',
      confirmButtonText: '确认重置',
      cancelButtonText: '取消',
      closeOnClickModal: false
    }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  resettingApiKeys.value = true
  try {
    const data = await galleryApi.resetApiKeys()
    syncOperationsApiKeys(data)
    visibleApiKeyIds.value = new Set(operationsApiKeys.value.map((item) => item.id))
    ElMessage.success('API Key 已重置')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '重置 API Key 失败')
  } finally {
    resettingApiKeys.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadAdminSettings(), loadSystemHealth(), loadCdnWarmStatus()])
})
</script>

<template>
  <div class="admin-card">
    <el-descriptions :column="1" border>
      <el-descriptions-item label="默认监听">127.0.0.1:8111</el-descriptions-item>
      <el-descriptions-item label="前端构建目录">/opt/moegallery/frontend/dist</el-descriptions-item>
      <el-descriptions-item label="默认存储目录">/opt/moegallery/storage</el-descriptions-item>
      <el-descriptions-item label="文件容量">{{ imageFileCapacity }}</el-descriptions-item>
      <el-descriptions-item label="配置前缀">AGMS_</el-descriptions-item>
      <el-descriptions-item label="后台鉴权">账号密码登录 + HttpOnly Cookie 会话。</el-descriptions-item>
    </el-descriptions>

    <div v-loading="settingsLoading" class="admin-settings-preferences">
      <section class="admin-preferences-panel">
        <div class="admin-preferences-body">
          <div class="admin-preference-section admin-account-panel">
            <el-alert
              v-if="adminPasswordChangeRequired"
              title="当前账号沿用了旧版默认密码，请设置新密码后再继续使用后台。"
              type="warning"
              show-icon
              :closable="false"
            />
            <div class="admin-preference-header">
              <div class="admin-preference-copy">
                <strong>管理员资料</strong>
                <span>点击头像可直接上传并覆盖。</span>
              </div>
              <el-button type="primary" :icon="Check" :loading="settingsSaving" @click="saveAdminPreferences">
                保存所有后台偏好
              </el-button>
            </div>
            <div class="admin-account-grid">
              <div class="admin-account-avatar">
                <el-upload
                  :auto-upload="false"
                  :show-file-list="false"
                  :accept="imageUploadAccept"
                  :on-change="(file) => uploadAdminAvatar(file.raw)"
                >
                  <button class="admin-account-avatar__button" type="button" :disabled="avatarUploading">
                    <img :src="adminAvatarUrl" alt="" />
                    <span class="admin-account-avatar__overlay">
                      <el-icon v-if="avatarUploading" class="is-loading"><Loading /></el-icon>
                      <span v-else>更换</span>
                    </span>
                  </button>
                </el-upload>
              </div>
              <div class="admin-account-form">
                <div class="admin-account-field">
                  <span>用户名</span>
                  <el-input v-model="adminUsername" maxlength="80" autocomplete="username" />
                </div>
                <div class="admin-account-field">
                  <span>新密码</span>
                  <el-input
                    v-model="adminPassword"
                    type="password"
                    show-password
                    minlength="6"
                    maxlength="128"
                    autocomplete="new-password"
                    :placeholder="adminPasswordChangeRequired ? '必须设置新密码' : '不修改则留空'"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="admin-preference-section home-slideshow-settings">
            <div class="admin-preference-header">
              <div class="admin-preference-copy">
                <strong>首页放映图片</strong>
                <span>指定首页参与放映的图片；未选择时首页自动随机展示图库图片。</span>
              </div>
              <div class="home-slideshow-picker-actions">
                <el-button type="primary" size="small" @click="openHomeSlideshowPicker">选择图片</el-button>
                <el-button size="small" :disabled="!homeSlideshowImageIds.length || settingsSaving" @click="clearHomeSlideshowImages">
                  清空选择
                </el-button>
              </div>
            </div>
            <el-dialog
              v-model="homeSlideshowPickerOpen"
              title="选择首页放映图片"
              width="960px"
              class="home-slideshow-picker-dialog"
              destroy-on-close
            >
              <div class="home-slideshow-picker-toolbar">
                <el-input
                  v-model="homeSlideshowImageQuery"
                  clearable
                  placeholder="搜索文件名、作者或来源"
                  @keyup.enter="searchHomeSlideshowImages"
                  @clear="searchHomeSlideshowImages"
                />
                <el-select
                  v-model="homeSlideshowWorkId"
                  class="home-slideshow-picker-filter"
                  clearable
                  filterable
                  remote
                  reserve-keyword
                  :loading="homeSlideshowWorkLoading"
                  :remote-method="loadHomeSlideshowWorkOptions"
                  placeholder="按作品筛选"
                  @change="handleHomeSlideshowWorkFilterChange"
                  @visible-change="(visible) => visible && loadHomeSlideshowWorkOptions()"
                >
                  <el-option
                    v-for="work in homeSlideshowWorkOptions"
                    :key="work.id"
                    :label="workOptionLabel(work)"
                    :value="work.id"
                  />
                </el-select>
                <el-select
                  v-model="homeSlideshowCharacterId"
                  class="home-slideshow-picker-filter"
                  clearable
                  filterable
                  remote
                  reserve-keyword
                  :loading="homeSlideshowCharacterLoading"
                  :remote-method="loadHomeSlideshowCharacterOptions"
                  placeholder="按角色筛选"
                  @change="handleHomeSlideshowCharacterFilterChange"
                  @visible-change="(visible) => visible && loadHomeSlideshowCharacterOptions()"
                >
                  <el-option
                    v-for="character in homeSlideshowCharacterOptions"
                    :key="character.id"
                    :label="characterOptionLabel(character)"
                    :value="character.id"
                  />
                </el-select>
                <el-select
                  v-model="homeSlideshowOrientation"
                  class="home-slideshow-picker-filter"
                  clearable
                  placeholder="按方向筛选"
                  @change="searchHomeSlideshowImages"
                >
                  <el-option v-for="orientation in orientationOptions" :key="orientation.value" :label="orientation.label" :value="orientation.value" />
                </el-select>
                <el-button type="primary" :loading="homeSlideshowImageLoading" @click="searchHomeSlideshowImages">搜索</el-button>
                <el-button
                  :disabled="!homeSlideshowImageQuery && !homeSlideshowWorkId && !homeSlideshowCharacterId && homeSlideshowOrientation === 'landscape'"
                  @click="resetHomeSlideshowPickerFilters"
                >
                  重置
                </el-button>
                <span class="home-slideshow-picker-count">已选择 {{ homeSlideshowImageIds.length }} / 24</span>
              </div>
              <div v-loading="homeSlideshowImageLoading" class="home-slideshow-picker-grid">
                <button
                  v-for="image in homeSlideshowPickerImages"
                  :key="image.id"
                  type="button"
                  class="home-slideshow-picker-card"
                  :class="{ 'is-selected': isHomeSlideshowImageSelected(image.id) }"
                  @click="toggleHomeSlideshowImage(image)"
                >
                  <img :src="imageThumbnailUrl(image)" alt="" loading="lazy" />
                  <span v-if="isHomeSlideshowImageSelected(image.id)" class="home-slideshow-picker-card__badge">
                    <el-icon><Check /></el-icon>
                  </span>
                  <span class="home-slideshow-picker-card__meta">
                    <strong>#{{ image.id }}</strong>
                    <span>{{ imageDisplayName(image) }}</span>
                    <small>{{ image.width }} x {{ image.height }} · {{ orientationLabel(image.orientation) }}</small>
                  </span>
                </button>
                <el-empty
                  v-if="!homeSlideshowImageLoading && !homeSlideshowPickerImages.length"
                  class="home-slideshow-picker-empty"
                  description="没有匹配图片"
                />
              </div>
              <div v-if="homeSlideshowPickerTotal > homeSlideshowPickerPageSize" class="home-slideshow-picker-pagination">
                <el-pagination
                  background
                  layout="prev, pager, next, jumper"
                  :current-page="homeSlideshowPickerPage"
                  :page-size="homeSlideshowPickerPageSize"
                  :total="homeSlideshowPickerTotal"
                  @current-change="handleHomeSlideshowPickerPage"
                />
              </div>
            </el-dialog>
            <div v-if="selectedHomeSlideshowImages.length" class="home-slideshow-admin-grid">
              <div v-for="(image, index) in selectedHomeSlideshowImages" :key="image.id" class="home-slideshow-admin-card">
                <img :src="imageThumbnailUrl(image)" alt="" />
                <div class="home-slideshow-admin-card__meta">
                  <strong>#{{ image.id }}</strong>
                  <span>{{ imageDisplayName(image) }}</span>
                </div>
                <div class="home-slideshow-admin-card__actions">
                  <el-button size="small" :disabled="index === 0" @click="moveHomeSlideshowImage(index, -1)">前移</el-button>
                  <el-button size="small" :disabled="index === selectedHomeSlideshowImages.length - 1" @click="moveHomeSlideshowImage(index, 1)">后移</el-button>
                  <el-button size="small" plain @click="removeHomeSlideshowImage(image.id)">移除</el-button>
                </div>
              </div>
            </div>
            <div v-else class="home-slideshow-empty">未指定图片时，首页自动随机展示图库图片。</div>
          </div>

          <div class="admin-preference-section home-hero-background-panel">
            <div class="admin-preference-header">
              <div class="admin-preference-copy">
                <strong>前台首卡背景</strong>
                <span>分别控制图片库、作品、角色和分级页面的首卡背景。</span>
              </div>
            </div>
            <div class="home-hero-background-grid">
              <div v-for="item in heroBackgroundItems" :key="item.key" class="home-hero-background-card">
                <div class="home-hero-background-card__head">
                  <div>
                    <strong>{{ item.label }}</strong>
                    <span>{{ item.hint }}</span>
                  </div>
                  <el-button size="small" :disabled="!item.imageId || item.uploading" @click="resetHeroBackground(item)">恢复默认</el-button>
                </div>
                <el-upload
                  :auto-upload="false"
                  :show-file-list="false"
                  :accept="imageUploadAccept"
                  :on-change="(file) => uploadHeroBackground(item, file.raw)"
                >
                  <button class="home-hero-background-button" type="button" :disabled="item.uploading">
                    <img :src="heroBackgroundUrl(item)" alt="" />
                    <span class="home-hero-background-button__overlay">
                      <el-icon v-if="item.uploading" class="is-loading"><Loading /></el-icon>
                      <span v-else>更换{{ item.label }}背景</span>
                    </span>
                  </button>
                </el-upload>
              </div>
            </div>
          </div>

          <div class="admin-preference-section admin-preference-block--inline">
            <div class="admin-preference-copy">
              <strong>图片管理显示</strong>
              <span>控制后台图片管理默认进入经典列表还是瀑布流视图。</span>
            </div>
            <el-radio-group
              v-model="imageManageViewMode"
              class="admin-preference-segment"
              :disabled="settingsSaving"
            >
              <el-radio-button v-for="mode in imageManageViewModes" :key="mode.value" :label="mode.value">
                {{ mode.label }}
              </el-radio-button>
            </el-radio-group>
          </div>

          <div class="admin-preference-section random-api-settings">
            <div class="admin-preference-header">
              <div class="admin-preference-copy">
                <strong>随机图片 API</strong>
                <span>无参数请求按设备应用默认方向，并始终只返回公开图片。</span>
              </div>
              <code>/api/images/random</code>
            </div>
            <div class="random-api-control-grid">
              <label class="random-api-control">
                <span>桌面默认方向</span>
                <el-select v-model="randomApiDesktopOrientation" :disabled="settingsSaving">
                  <el-option
                    v-for="item in randomApiOrientationOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </label>
              <label class="random-api-control">
                <span>手机默认方向</span>
                <el-select v-model="randomApiMobileOrientation" :disabled="settingsSaving">
                  <el-option
                    v-for="item in randomApiOrientationOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </label>
              <label class="random-api-control">
                <span>默认分级</span>
                <el-select v-model="randomApiDefaultRating" :disabled="settingsSaving">
                  <el-option
                    v-for="item in randomApiRatingOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </label>
              <label class="random-api-control">
                <span>默认输出</span>
                <el-select v-model="randomApiDefaultVariant" :disabled="settingsSaving">
                  <el-option
                    v-for="item in randomApiVariantOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </label>
            </div>
          </div>

          <div class="admin-preference-section upload-queue-settings">
            <div class="admin-preference-copy">
              <strong>上传队列参数</strong>
              <span>控制后台上传任务、转码任务的并发领取和处理节奏。</span>
            </div>
            <div class="upload-queue-control-grid">
              <div class="upload-queue-control">
                <div class="upload-queue-control__copy">
                  <strong>处理 worker</strong>
                  <span>{{ uploadWorkerHint }}</span>
                </div>
                <el-input-number
                  v-model="uploadWorkerCount"
                  :min="1"
                  :max="uploadWorkerLimit"
                  :step="1"
                  controls-position="right"
                />
              </div>
              <div class="upload-queue-control">
                <div class="upload-queue-control__copy">
                  <strong>单 worker 领取数</strong>
                  <span>每个 worker 单轮最多连续领取的任务数。</span>
                </div>
                <el-input-number
                  v-model="uploadClaimBatchSize"
                  :min="1"
                  :max="100"
                  :step="1"
                  controls-position="right"
                />
              </div>
              <div class="upload-queue-control">
                <div class="upload-queue-control__copy">
                  <strong>最大尝试次数</strong>
                  <span>新任务自动处理失败后的总尝试次数。</span>
                </div>
                <el-input-number
                  v-model="uploadTaskMaxAttempts"
                  :min="1"
                  :max="10"
                  :step="1"
                  controls-position="right"
                />
              </div>
              <div class="upload-queue-control">
                <div class="upload-queue-control__copy">
                  <strong>失败文件保留</strong>
                  <span>失败任务可手动重试的保留天数。</span>
                </div>
                <el-input-number
                  v-model="uploadFailedRetentionDays"
                  :min="1"
                  :max="90"
                  :step="1"
                  controls-position="right"
                />
              </div>
            </div>
          </div>

          <div class="admin-preference-section github-proxy-settings">
            <div class="admin-preference-copy">
              <strong>GitHub 更新检查</strong>
              <span>用于系统健康获取最新版本；留空则直接访问 GitHub。</span>
            </div>
            <el-input
              v-model="githubProxyUrl"
              clearable
              maxlength="500"
              placeholder="例如：https://gh-proxy.example.com/"
            />
          </div>

          <div class="admin-preference-section cdn-warm-settings">
            <div class="cdn-warm-panel">
              <div class="admin-preference-header cdn-warm-panel__header">
                <div class="admin-preference-copy">
                  <strong>CDN 图片预热</strong>
                  <span>模拟浏览器访问公开图片，识别 ESA、EdgeOne 与 Cloudflare 的真实缓存状态；私有、隐藏和分享链接不会进入队列。</span>
                </div>
                <div class="cdn-warm-actions">
                  <el-button class="cdn-warm-button cdn-warm-button--secondary" size="small" :icon="Refresh" :loading="cdnWarmLoading" @click="loadCdnWarmStatus">刷新状态</el-button>
                  <el-button class="cdn-warm-button cdn-warm-button--save" size="small" :loading="cdnWarmSaving" @click="saveCdnWarmConfig">保存并探测</el-button>
                </div>
              </div>

              <div class="cdn-warm-toggle">
                <div>
                  <strong>启用自动预热</strong>
                  <span>新增公开图片会自动入队；现有缩略图分批补齐，缓存到期前自动续热。</span>
                </div>
                <el-switch v-model="cdnWarmEnabled" size="large" />
              </div>

              <label class="cdn-warm-domain">
                <span>CDN HTTPS 域名</span>
                <el-input
                  v-model="cdnWarmBaseUrl"
                  clearable
                  maxlength="500"
                  placeholder="例如：https://anime.example.com"
                  :disabled="cdnWarmSaving"
                />
                <small>仅接受已绑定域名；127、localhost、IP 或直连源站会被自动拒绝。</small>
              </label>

              <div v-if="cdnWarmStatus" class="cdn-warm-status-grid">
                <div class="cdn-warm-stat">
                  <span>预热状态</span>
                  <strong>{{ cdnWarmStatus.config?.enabled ? '自动运行中' : '尚未启用' }}</strong>
                </div>
                <div class="cdn-warm-stat">
                  <span>队列</span>
                  <strong>{{ cdnWarmStatus.queued || 0 }} <small>等待</small></strong>
                </div>
                <div class="cdn-warm-stat">
                  <span>缓存结果</span>
                  <strong>{{ cdnWarmStatus.success || 0 }} <small>成功</small></strong>
                </div>
                <div class="cdn-warm-stat">
                  <span>Worker</span>
                  <strong :class="{ 'is-running': cdnWarmStatus.worker_alive }">{{ cdnWarmStatus.worker_alive ? '运行中' : '待机' }}</strong>
                </div>
              </div>

              <div v-if="cdnWarmStatus" class="cdn-warm-progress">
                <div class="cdn-warm-progress__heading">
                  <div>
                    <strong>公开缩略图预热进度</strong>
                    <span>已就绪 {{ cdnWarmStatus.coverage_fresh || 0 }} / {{ cdnWarmStatus.coverage_total || 0 }}，每 {{ Math.round((cdnWarmStatus.rewarm_after_seconds || 0) / 86400) || '-' }} 天自动续热。</span>
                  </div>
                  <b>{{ cdnWarmProgress.toFixed(1) }}%</b>
                </div>
                <el-progress :percentage="cdnWarmProgress" :stroke-width="14" :show-text="false" :status="cdnWarmProgress >= 100 ? 'success' : undefined" />
              </div>

              <div v-if="cdnWarmStatus?.recent_tasks?.length" class="cdn-warm-recent">
                <span class="cdn-warm-recent__label">最近任务</span>
                <span v-for="task in cdnWarmStatus.recent_tasks.slice(0, 4)" :key="task.id" class="cdn-warm-task-chip">
                  #{{ task.image_id }} · {{ cdnProviderLabel(task.provider) }}
                  <el-tag size="small" :type="cdnCacheStatusType(task.cache_status)">{{ task.cache_status || task.status }}</el-tag>
                </span>
              </div>

              <div class="cdn-warm-actions cdn-warm-actions--footer">
                <el-button class="cdn-warm-button cdn-warm-button--probe" size="small" :loading="cdnWarmLoading" :disabled="!cdnWarmStatus?.config?.enabled" @click="probeCdnWarm">探测 CDN</el-button>
                <el-button class="cdn-warm-button cdn-warm-button--seed" size="small" :loading="cdnWarmSeeding" :disabled="!cdnWarmStatus?.config?.enabled" @click="seedCdnWarmThumbnails">预热全部公开缩略图</el-button>
              </div>
            </div>
          </div>

          <div class="admin-preference-section api-key-settings">
            <div class="admin-preference-header">
              <div class="admin-preference-copy">
                <strong>运维 API Key</strong>
                <span>用于脚本、监控和自动化任务调用后台 API；重置后旧 Key 立即失效。</span>
              </div>
              <div class="api-key-actions">
                <el-button size="small" type="primary" :icon="Plus" @click="openCreateApiKey">新建 Key</el-button>
                <el-button size="small" plain :loading="resettingApiKeys" @click="resetOperationsApiKeys">
                  全部重置
                </el-button>
              </div>
            </div>
            <div v-if="operationsApiKeys.length" class="api-key-list">
              <div v-for="item in operationsApiKeys" :key="item.id" class="api-key-row">
                <div class="api-key-row__heading">
                  <strong class="api-key-row__name">{{ item.name }}</strong>
                  <el-tag v-if="item.full_access" size="small" type="danger">全部权限</el-tag>
                  <el-tag v-else-if="item.status === 'expired'" size="small" type="warning">已过期</el-tag>
                  <el-tag v-else size="small" type="success">使用中</el-tag>
                </div>
                <div class="api-key-row__secret">
                  <el-input
                    :model-value="item.key"
                    :type="isApiKeyVisible(item.id) ? 'text' : 'password'"
                    readonly
                    spellcheck="false"
                    title="双击复制 API Key"
                    @dblclick="copyApiKey(item.key)"
                  />
                  <el-button
                    size="small"
                    :title="isApiKeyVisible(item.id) ? '隐藏 Key' : '显示 Key'"
                    @click="toggleApiKeyVisible(item.id)"
                  >
                    {{ isApiKeyVisible(item.id) ? '隐藏' : '显示' }}
                  </el-button>
                  <el-button
                    size="small"
                    :icon="Refresh"
                    :loading="rotatingApiKeyId === item.id"
                    title="重新生成 Key"
                    @click="rotateOperationsApiKey(item)"
                  />
                  <el-button size="small" :icon="Edit" title="修改 Key" @click="openEditApiKey(item)" />
                  <el-button size="small" :icon="Delete" title="撤销 Key" @click="revokeOperationsApiKey(item)" />
                </div>
                <div class="api-key-row__meta">
                  <span>权限：{{ item.full_access ? '全部系统权限' : item.scopes.map(apiKeyScopeLabel).join('、') }}</span>
                  <span>有效期：{{ formatApiKeyTime(item.expires_at) }}</span>
                  <span>最近调用：{{ formatApiKeyTime(item.last_used_at, '尚未调用') }}<template v-if="item.last_used_ip"> · {{ item.last_used_ip }}</template></span>
                </div>
              </div>
            </div>
            <div v-else class="api-key-empty">
              当前未配置 API Key，点击“新建 Key”后按用途授予权限。
            </div>
          </div>
        </div>
      </section>
    </div>

    <el-dialog
      v-model="apiKeyDialogOpen"
      :title="editingApiKeyId ? '修改 API Key' : '新建 API Key'"
      width="min(620px, calc(100vw - 32px))"
      append-to-body
      destroy-on-close
    >
      <div class="api-key-editor">
        <label class="api-key-editor__field">
          <span>名称</span>
          <el-input v-model="apiKeyForm.name" maxlength="80" placeholder="例如：上传节点、只读监控" />
        </label>
        <div class="api-key-editor__field">
          <div class="api-key-editor__label">
            <span>权限</span>
            <el-button link type="primary" @click="selectAllApiKeyScopes">选择全部权限</el-button>
          </div>
          <el-checkbox-group v-model="apiKeyForm.scopes" class="api-key-scope-grid">
            <el-checkbox v-for="scope in apiKeyScopes" :key="scope.value" :value="scope.value" border>
              <span class="api-key-scope-option">
                <strong>{{ scope.label }}</strong>
                <small>{{ scope.description }}</small>
              </span>
            </el-checkbox>
          </el-checkbox-group>
          <el-alert
            v-if="apiKeyForm.scopes.length === apiKeyScopes.length && apiKeyScopes.length"
            title="已选择全部权限，此 Key 可以控制整个系统。"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>
        <label class="api-key-editor__field">
          <span>有效期</span>
          <el-date-picker
            v-model="apiKeyForm.expires_at"
            type="datetime"
            placeholder="留空表示永不过期"
            :disabled-date="(date) => date.getTime() < Date.now() - 86400000"
          />
        </label>
      </div>
      <template #footer>
        <el-button @click="apiKeyDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="apiKeySaving" @click="saveApiKey">保存</el-button>
      </template>
    </el-dialog>

    <div class="section-title">
      <div>
        <h2>系统健康</h2>
        <span class="muted">检查数据库、存储目录和图像处理依赖。</span>
      </div>
      <div class="system-health-actions">
        <el-button :icon="Refresh" :loading="healthLoading" @click="loadSystemHealth(true)">刷新</el-button>
        <el-button plain :loading="rotatingSecret" @click="rotateLoginSecret">轮换登录密钥</el-button>
      </div>
    </div>
    <div v-if="healthError" class="system-health-state system-health-state--error">
      <div>
        <strong>系统健康信息加载失败</strong>
        <span>{{ healthError }}</span>
      </div>
      <el-button :icon="Refresh" size="small" @click="loadSystemHealth(true)">重试</el-button>
    </div>
    <div v-else-if="healthLoading && !health" class="system-health-state">
      <div>
        <strong>正在检查系统状态</strong>
        <span>正在读取数据库、存储目录和图像处理依赖。</span>
      </div>
    </div>
    <div v-else-if="!health" class="system-health-state">
      <div>
        <strong>暂无系统健康信息</strong>
        <span>点击刷新重新获取后台环境状态。</span>
      </div>
      <el-button :icon="Refresh" size="small" @click="loadSystemHealth(true)">刷新</el-button>
    </div>
    <div v-if="health" v-loading="healthLoading" class="system-health-grid">
      <div
        v-for="card in healthCards"
        :key="card.key"
        class="system-health-card"
        :class="`system-health-card--${card.tone}`"
      >
        <span class="system-health-card__label">{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.detail }}</small>
      </div>
    </div>
  </div>
</template>
