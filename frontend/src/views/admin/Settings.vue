<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Loading, Refresh } from '@element-plus/icons-vue'
import { adminAvatarUrlFromImage, clearAuthSession, setAuthSession, storageUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
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
const uploadClaimBatchSize = ref(1)
const adminUsername = ref('')
const adminPassword = ref('')
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

const adminAvatarUrl = computed(() => adminAvatarUrlFromImage(adminAvatarImage.value) || '/avatar.webp')
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
  const database = data.database || {}
  const databaseDetail =
    database.dialect === 'sqlite'
      ? `SQLite · ${formatBytes(database.size_bytes)}`
      : `${database.dialect || 'Database'} · ${database.driver || 'driver'}`
  const fileHealth = formatImageFileHealth(consistency.image_records, original, preview, thumbnail)
  const missingFileDirs = [
    ['原图', original.exists],
    ['预览图', preview.exists],
    ['缩略图', thumbnail.exists]
  ]
    .filter(([, exists]) => !exists)
    .map(([label]) => label)
  const fileHealthDetail = missingFileDirs.length
    ? `${missingFileDirs.join('、')}目录缺失`
    : fileHealth.message
  const filesReady = missingFileDirs.length === 0 && fileHealth.complete
  const migrationReady = migration.up_to_date !== false
  const versionDetail = application.update_available
    ? `最新 ${latestRelease.version || '未知'} 可用`
    : latestRelease.available
      ? `最新 ${latestRelease.version || '未知'} · 迁移 ${migrationReady ? '已同步' : '待执行'}`
      : `迁移 ${migrationReady ? '已同步' : '待执行'}`
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
      value: `${data.upload_queue?.worker_count ?? uploadWorkerCount.value} workers`,
      detail: `单轮领取 ${data.upload_queue?.claim_batch_size ?? uploadClaimBatchSize.value}`,
      tone: 'info'
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

function formatImageFileHealth(imageRecords, original, preview, thumbnail) {
  const expected = Number(imageRecords || 0)
  const sections = [
    ['原图', Number(original.file_count || 0)],
    ['预览图', Number(preview.file_count || 0)],
    ['缩略图', Number(thumbnail.file_count || 0)]
  ]
  const issues = sections
    .map(([label, count]) => {
      const diff = count - expected
      if (diff < 0) return `${label}缺失 ${Math.abs(diff)} 个`
      if (diff > 0) return `${label}多出 ${diff} 个`
      return ''
    })
    .filter(Boolean)
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
  adminAvatarImageId.value = data.admin_avatar_image_id || null
  adminAvatarImage.value = data.admin_avatar_image || null
  syncHomeSlideshowImages(data)
  syncHeroBackgrounds(data)
  setAuthSession({ username: adminUsername.value, avatar_image: adminAvatarImage.value })
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
  return storageUrl(item.image?.preview_path || item.image?.file_path || item.image?.thumbnail_path) || item.fallback
}

function imageDisplayName(image) {
  return image?.original_filename || image?.filename || `图片 ${image?.id || ''}`
}

function imageThumbnailUrl(image) {
  return storageUrl(image?.thumbnail_path || image?.preview_path || image?.file_path)
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
    uploadClaimBatchSize.value = data.upload_claim_batch_size || 1
    syncAccount(data)
    setImageManageViewMode(imageManageViewMode.value)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载设置失败')
  } finally {
    settingsLoading.value = false
  }
}

async function saveAdminPreferences() {
  if (!adminUsername.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  settingsSaving.value = true
  try {
    const payload = {
      admin_username: adminUsername.value.trim(),
      admin_avatar_image_id: adminAvatarImageId.value || undefined,
      home_slideshow_image_ids: homeSlideshowImageIds.value,
      image_manage_view_mode: normalizeImageManageViewMode(imageManageViewMode.value),
      upload_worker_count: uploadWorkerCount.value,
      upload_claim_batch_size: uploadClaimBatchSize.value
    }
    heroBackgroundItems.value.forEach((item) => {
      if (item.imageId) payload[item.imageIdField] = item.imageId
    })
    if (adminPassword.value) payload.admin_password = adminPassword.value
    const data = await galleryApi.updateSettings(payload)
    adminPassword.value = ''
    imageManageViewMode.value = normalizeImageManageViewMode(data.image_manage_view_mode)
    uploadWorkerCount.value = data.upload_worker_count
    uploadClaimBatchSize.value = data.upload_claim_batch_size
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

async function loadSystemHealth() {
  healthLoading.value = true
  healthError.value = ''
  try {
    health.value = await galleryApi.systemHealth()
  } catch (error) {
    healthError.value = error?.response?.data?.detail || error?.message || '加载系统健康检查失败'
    ElMessage.error(healthError.value)
  } finally {
    healthLoading.value = false
  }
}

async function rotateLoginSecret() {
  await ElMessageBox.confirm(
    '轮换后所有后台会话都会立即失效，需要重新登录。确认继续？',
    '轮换登录密钥',
    {
      type: 'warning',
      confirmButtonText: '确认轮换',
      cancelButtonText: '取消',
      closeOnClickModal: false
    }
  )
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

onMounted(async () => {
  await Promise.all([loadAdminSettings(), loadSystemHealth()])
})
</script>

<template>
  <div class="admin-card">
    <el-descriptions :column="1" border>
      <el-descriptions-item label="后端监听">127.0.0.1:8000</el-descriptions-item>
      <el-descriptions-item label="前端构建目录">/opt/anime-gallery/frontend/dist</el-descriptions-item>
      <el-descriptions-item label="默认存储目录">/opt/anime-gallery/storage</el-descriptions-item>
      <el-descriptions-item label="文件容量">{{ imageFileCapacity }}</el-descriptions-item>
      <el-descriptions-item label="配置前缀">AGMS_</el-descriptions-item>
      <el-descriptions-item label="后台鉴权">账号密码登录 + HttpOnly Cookie 会话。</el-descriptions-item>
    </el-descriptions>

    <div v-loading="settingsLoading" class="admin-settings-preferences">
      <section class="admin-preferences-panel">
        <div class="admin-preferences-body">
          <div class="admin-preference-section admin-account-panel">
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
                    placeholder="不修改则留空"
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
                <el-button type="primary" :loading="homeSlideshowImageLoading" @click="searchHomeSlideshowImages">搜索</el-button>
                <el-button
                  :disabled="!homeSlideshowImageQuery && !homeSlideshowWorkId && !homeSlideshowCharacterId"
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
                    <small>{{ image.width }} x {{ image.height }}</small>
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

          <div class="admin-preference-section upload-queue-settings">
            <div class="admin-preference-copy">
              <strong>上传队列参数</strong>
              <span>控制后台上传任务、转码任务的并发领取和处理节奏。</span>
            </div>
            <div class="upload-queue-control-grid">
              <div class="upload-queue-control">
                <div class="upload-queue-control__copy">
                  <strong>处理 worker</strong>
                  <span>同一时间并发处理的上传任务数。</span>
                </div>
                <el-input-number
                  v-model="uploadWorkerCount"
                  :min="1"
                  :max="96"
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
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="section-title">
      <div>
        <h2>系统健康</h2>
        <span class="muted">检查数据库、存储目录和图像处理依赖。</span>
      </div>
      <div class="system-health-actions">
        <el-button :icon="Refresh" :loading="healthLoading" @click="loadSystemHealth">刷新</el-button>
        <el-button plain :loading="rotatingSecret" @click="rotateLoginSecret">轮换登录密钥</el-button>
      </div>
    </div>
    <div v-if="healthError" class="system-health-state system-health-state--error">
      <div>
        <strong>系统健康信息加载失败</strong>
        <span>{{ healthError }}</span>
      </div>
      <el-button :icon="Refresh" size="small" @click="loadSystemHealth">重试</el-button>
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
      <el-button :icon="Refresh" size="small" @click="loadSystemHealth">刷新</el-button>
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
