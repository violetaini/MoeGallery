<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Collection, Edit, Link, Picture, Plus, Star, Timer, UploadFilled, User } from '@element-plus/icons-vue'
import { storageUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import ResponsiveImage from '../../components/ResponsiveImage.vue'
import ImageMasonry from '../../components/ImageMasonry.vue'
import { imageUploadAccept } from '../../constants/uploadFormats'
import { displayId } from '../../utils/displayId'

const CHARACTER_CARD_MIN_WIDTH = 180
const CHARACTER_GRID_GAP = 16
const CHARACTER_MAX_PAGE_SIZE = 24
const CHARACTER_GRID_ROWS = 2

const route = useRoute()
const router = useRouter()
const work = ref(null)
const images = ref([])
const avatarImages = ref([])
const characters = ref([])
const characterTotal = ref(0)
const characterPage = ref(1)
const characterSectionRef = ref(null)
const characterColumnCount = ref(1)
const imageTotal = ref(0)
const imagePage = ref(1)
const imagePageSize = 24
const pageLoading = ref(false)
const characterLoading = ref(false)
const imageLoading = ref(false)
const uploading = ref(false)
const uploadingAvatar = ref(false)
const uploadFiles = ref([])
const characterDialog = ref(false)
const characterSaving = ref(false)
const workDialog = ref(false)
const workSaving = ref(false)
const uploadForm = reactive({
  rating: 'safe',
  is_public: true,
  source_url: '',
  artist_name: ''
})
const characterForm = reactive({
  name: '',
  original_name: '',
  aliases: '',
  description: '',
  avatar_image_id: null
})
const workForm = reactive({
  name: '',
  original_name: '',
  aliases: '',
  description: '',
  tagline: '',
  production_year: null,
  run_time_minutes: null,
  community_rating: null,
  content_rating: '',
  genres: '',
  studios: '',
  official_site: '',
  status: '',
  sort_order: 0
})

const workId = computed(() => Number(route.params.id))
const poster = computed(() => work.value?.cover_image || null)
const backdrop = computed(() => storageUrl(work.value?.backdrop_image?.preview_path || work.value?.cover_image?.preview_path || work.value?.cover_image?.thumbnail_path))
const heroStyle = computed(() => (backdrop.value ? { '--work-backdrop-image': `url("${backdrop.value}")` } : {}))
const runtimeText = computed(() => {
  if (!work.value?.run_time_minutes) return ''
  return `${work.value.run_time_minutes} 分钟`
})
const ratingText = computed(() => {
  if (!work.value?.community_rating) return ''
  return Number(work.value.community_rating).toFixed(1)
})
const characterPageSize = computed(() => {
  const availableSlots = Math.max(1, characterColumnCount.value * CHARACTER_GRID_ROWS - 1)
  return Math.min(CHARACTER_MAX_PAGE_SIZE, availableSlots)
})
const currentCharacterAvatar = computed(() => {
  const selected = avatarImages.value.find((image) => image.id === characterForm.avatar_image_id)
  return storageUrl(selected?.thumbnail_path || selected?.preview_path)
})
const avatarImageDisplayIds = computed(() => new Map(avatarImages.value.map((image, index) => [image.id, displayId(index)])))

let characterResizeObserver
let characterResizeFallbackActive = false

function avatarImageOptionLabel(image) {
  return `${image.original_filename || image.filename || '未命名图片'} · 序号 ${avatarImageDisplayIds.value.get(image.id) || '-'}`
}

async function loadWork() {
  pageLoading.value = true
  try {
    work.value = await galleryApi.work(workId.value)
  } finally {
    pageLoading.value = false
  }
}

async function loadImages() {
  imageLoading.value = true
  try {
    const data = await galleryApi.images({
      page: imagePage.value,
      page_size: imagePageSize,
      public_only: false,
      work_id: workId.value
    })
    images.value = data.items
    imageTotal.value = data.total
  } finally {
    imageLoading.value = false
  }
}

async function loadAvatarImages() {
  const data = await galleryApi.images({ page_size: 100, public_only: false })
  avatarImages.value = data.items
}

async function loadCharacters() {
  characterLoading.value = true
  try {
    const data = await galleryApi.characters({
      page: characterPage.value,
      page_size: characterPageSize.value,
      work_id: workId.value
    })
    characters.value = data.items
    characterTotal.value = data.total
  } finally {
    characterLoading.value = false
  }
}

function changeCharacterPage(nextPage) {
  characterPage.value = nextPage
  loadCharacters()
}

function changeImagePage(nextPage) {
  imagePage.value = nextPage
  loadImages()
}

function updateCharacterColumns() {
  const section = characterSectionRef.value
  if (!section || typeof window === 'undefined') return
  const styles = window.getComputedStyle(section)
  const horizontalPadding = Number.parseFloat(styles.paddingLeft) + Number.parseFloat(styles.paddingRight)
  const contentWidth = Math.max(0, section.clientWidth - horizontalPadding)
  const nextColumns = Math.max(
    1,
    Math.floor((contentWidth + CHARACTER_GRID_GAP) / (CHARACTER_CARD_MIN_WIDTH + CHARACTER_GRID_GAP))
  )
  characterColumnCount.value = nextColumns
}

function startCharacterObserver(section) {
  stopCharacterObserver()
  updateCharacterColumns()
  if (window.ResizeObserver) {
    characterResizeObserver = new ResizeObserver(updateCharacterColumns)
    characterResizeObserver.observe(section)
  } else {
    window.addEventListener('resize', updateCharacterColumns)
    characterResizeFallbackActive = true
  }
}

function stopCharacterObserver() {
  if (characterResizeObserver) {
    characterResizeObserver.disconnect()
    characterResizeObserver = null
  }
  if (characterResizeFallbackActive) {
    window.removeEventListener('resize', updateCharacterColumns)
    characterResizeFallbackActive = false
  }
}

function openCreateCharacter() {
  Object.assign(characterForm, {
    name: '',
    original_name: '',
    aliases: '',
    description: '',
    avatar_image_id: null
  })
  if (!avatarImages.value.length) {
    loadAvatarImages()
  }
  characterDialog.value = true
}

function openEditWork() {
  if (!work.value) return
  Object.assign(workForm, {
    name: work.value.name || '',
    original_name: work.value.original_name || '',
    aliases: work.value.aliases || '',
    description: work.value.description || '',
    tagline: work.value.tagline || '',
    production_year: work.value.production_year ?? null,
    run_time_minutes: work.value.run_time_minutes ?? null,
    community_rating: work.value.community_rating ?? null,
    content_rating: work.value.content_rating || '',
    genres: work.value.genres || '',
    studios: work.value.studios || '',
    official_site: work.value.official_site || '',
    status: work.value.status || '',
    sort_order: work.value.sort_order ?? 0
  })
  workDialog.value = true
}

async function saveWork() {
  if (!workForm.name.trim()) {
    ElMessage.warning('请填写作品名')
    return
  }
  workSaving.value = true
  try {
    await galleryApi.updateWork(workId.value, {
      ...workForm,
      name: workForm.name.trim(),
      production_year: workForm.production_year || null,
      run_time_minutes: workForm.run_time_minutes || null,
      community_rating: workForm.community_rating || null
    })
    workDialog.value = false
    ElMessage.success('作品资料已保存')
    await loadWork()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存作品失败')
  } finally {
    workSaving.value = false
  }
}

async function uploadCharacterAvatar(upload) {
  uploadingAvatar.value = true
  const data = new FormData()
  data.append('files', upload.file)
  data.append('rating', 'safe')
  data.append('is_public', 'true')
  data.append('work_ids', '')
  data.append('character_ids', '')
  try {
    const result = await galleryApi.uploadImages(data)
    const image = result.items[0]?.image
    if (image) {
      characterForm.avatar_image_id = image.id
      if (!avatarImages.value.some((item) => item.id === image.id)) {
        avatarImages.value.unshift(image)
      }
      ElMessage.success('头像已上传')
    }
    upload.onSuccess?.(result)
    return result
  } catch (error) {
    upload.onError?.(error)
    throw error
  } finally {
    uploadingAvatar.value = false
  }
}

async function saveCharacter() {
  characterSaving.value = true
  try {
    await galleryApi.createCharacter({
      work_id: workId.value,
      name: characterForm.name,
      original_name: characterForm.original_name,
      aliases: characterForm.aliases,
      description: characterForm.description,
      avatar_image_id: characterForm.avatar_image_id || null
    })
    characterDialog.value = false
    ElMessage.success('角色已创建')
    characterPage.value = 1
    await loadCharacters()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '创建角色失败')
  } finally {
    characterSaving.value = false
  }
}

async function submitUpload() {
  if (!uploadFiles.value.length) {
    ElMessage.warning('请选择图片')
    return
  }
  uploading.value = true
  const data = new FormData()
  uploadFiles.value.forEach((file) => {
    if (file.raw) data.append('files', file.raw)
  })
  data.append('work_ids', String(workId.value))
  data.append('character_ids', '')
  data.append('rating', uploadForm.rating)
  data.append('is_public', String(uploadForm.is_public))
  if (uploadForm.source_url) data.append('source_url', uploadForm.source_url)
  if (uploadForm.artist_name) data.append('artist_name', uploadForm.artist_name)
  try {
    const result = await galleryApi.uploadImages(data)
    ElMessage.success(`已上传 ${result.items.length} 张图片`)
    uploadFiles.value = []
    await Promise.all([loadWork(), loadImages()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '上传失败')
    throw error
  } finally {
    uploading.value = false
  }
}

watch(characterSectionRef, async (section) => {
  await nextTick()
  if (!section) {
    stopCharacterObserver()
    return
  }
  startCharacterObserver(section)
}, { flush: 'post' })

onMounted(() => {
  if (characterSectionRef.value) {
    startCharacterObserver(characterSectionRef.value)
  }
})

onBeforeUnmount(() => {
  stopCharacterObserver()
})

watch(workId, async () => {
  if (!Number.isFinite(workId.value) || workId.value <= 0) return
  characters.value = []
  characterPage.value = 1
  imagePage.value = 1
  await Promise.all([loadWork(), loadImages(), loadCharacters()])
}, { immediate: true })

watch(characterPageSize, async (nextSize, previousSize) => {
  if (nextSize === previousSize || !work.value) return
  const lastPage = Math.max(1, Math.ceil(characterTotal.value / nextSize))
  if (characterPage.value > lastPage) {
    characterPage.value = lastPage
  }
  await loadCharacters()
})
</script>

<template>
  <el-skeleton v-if="pageLoading && !work" :rows="10" animated />
  <div v-else-if="work" class="work-detail admin-detail-page">
    <div class="admin-detail-topbar">
      <el-button :icon="ArrowLeft" @click="router.push('/admin/works')">返回作品管理</el-button>
    </div>

    <section class="work-hero jellyfin-work-hero" :style="heroStyle">
      <div class="work-poster-frame">
        <ResponsiveImage
          v-if="poster"
          :image="poster"
          :alt="work.name"
          img-class="work-poster"
          variant="preview"
          prefer-hdr
          prefer-animated
        />
        <div v-else class="work-poster work-poster--empty"></div>
      </div>
      <div class="work-hero-copy">
        <div class="work-kicker">
          <el-icon><Collection /></el-icon>
          <span>后台作品主页</span>
        </div>
        <h1>{{ work.name }}</h1>
        <p v-if="work.original_name" class="work-original">{{ work.original_name }}</p>
        <p v-if="work.tagline" class="work-tagline">{{ work.tagline }}</p>
        <div class="work-meta">
          <el-tag v-if="work.production_year" effect="dark">{{ work.production_year }}</el-tag>
          <el-tag v-if="runtimeText" effect="dark"><el-icon><Timer /></el-icon>{{ runtimeText }}</el-tag>
          <el-tag v-if="ratingText" effect="dark"><el-icon><Star /></el-icon>{{ ratingText }}</el-tag>
          <el-tag effect="dark"><el-icon><User /></el-icon>{{ characterTotal }} 位角色</el-tag>
          <el-tag effect="dark"><el-icon><Picture /></el-icon>{{ imageTotal }} 张图片</el-tag>
        </div>
        <div class="work-actions">
          <el-button type="primary" :icon="Edit" @click="openEditWork">编辑资料</el-button>
          <el-button v-if="work.official_site" tag="a" :href="work.official_site" target="_blank" rel="noreferrer" type="primary" :icon="Link">
            外部资料
          </el-button>
        </div>
        <div class="work-overview">
          <h2>概览</h2>
          <p>{{ work.description || '暂无简介' }}</p>
        </div>
        <div class="chip-row">
          <el-tag type="success">当前上传自动附带作品：{{ work.name }}</el-tag>
        </div>
      </div>
    </section>

    <section ref="characterSectionRef" class="media-section">
      <div class="section-title media-section-title">
        <div>
          <h2>角色管理</h2>
          <span class="muted">每页 {{ characterPageSize }} 位角色，共 {{ characterTotal }} 位。添加入口固定在第一格，点击角色头像进入角色主页上传。</span>
        </div>
        <el-pagination
          v-if="characterTotal > characterPageSize"
          v-model:current-page="characterPage"
          small
          background
          layout="prev, pager, next"
          :page-size="characterPageSize"
          :total="characterTotal"
          @current-change="changeCharacterPage"
        />
      </div>
      <el-skeleton v-if="characterLoading" :rows="4" animated />
      <div v-else class="grid-cards work-character-grid admin-work-character-grid">
        <button type="button" class="entity-card admin-character-add-card" @click="openCreateCharacter">
          <span class="admin-character-add-card__icon">
            <el-icon><Plus /></el-icon>
          </span>
          <strong>添加角色</strong>
          <span>创建后自动绑定当前作品</span>
        </button>
        <RouterLink
          v-for="item in characters"
          :key="item.id"
          class="entity-card entity-card--character admin-character-card"
          :to="{ path: `/admin/characters/${item.id}`, query: { fromWork: work.id } }"
        >
          <div class="entity-card__media">
            <ResponsiveImage
              v-if="item.avatar_image"
              :image="item.avatar_image"
              :alt="item.name"
              img-class="entity-thumb entity-thumb--character"
              variant="thumbnail"
              loading="lazy"
            />
            <div v-else class="entity-thumb entity-thumb--character"></div>
          </div>
          <div class="entity-card-body">
            <h3>{{ item.name }}</h3>
            <div class="muted">{{ item.original_name || '当前作品角色' }}</div>
          </div>
        </RouterLink>
      </div>
    </section>

    <section class="media-section admin-detail-upload-panel">
      <div class="section-title media-section-title">
        <div>
          <h2>上传图片</h2>
          <span class="muted">这里上传只自动绑定当前作品，不会重复写角色信息。</span>
        </div>
      </div>
      <div class="admin-detail-upload-grid">
        <el-upload
          v-model:file-list="uploadFiles"
          drag
          multiple
          :show-file-list="true"
          :auto-upload="false"
          :accept="imageUploadAccept"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入图片或点击选择</div>
        </el-upload>
        <el-form label-width="82px">
          <el-form-item label="作者">
            <el-input v-model="uploadForm.artist_name" />
          </el-form-item>
          <el-form-item label="来源">
            <el-input v-model="uploadForm.source_url" />
          </el-form-item>
          <el-form-item label="分级">
            <el-radio-group v-model="uploadForm.rating">
              <el-radio-button label="safe">safe</el-radio-button>
              <el-radio-button label="sensitive">sensitive</el-radio-button>
              <el-radio-button label="hidden">hidden</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="公开">
            <el-switch v-model="uploadForm.is_public" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="uploading" :disabled="!uploadFiles.length" @click="submitUpload">上传到当前作品</el-button>
          </el-form-item>
        </el-form>
      </div>
    </section>

    <section class="media-section">
      <div class="section-title media-section-title">
        <div>
          <h2>当前图片</h2>
          <span class="muted">每页 {{ imagePageSize }} 张，共 {{ imageTotal }} 张</span>
        </div>
        <el-pagination
          v-if="imageTotal > imagePageSize"
          v-model:current-page="imagePage"
          small
          background
          layout="prev, pager, next"
          :page-size="imagePageSize"
          :total="imageTotal"
          @current-change="changeImagePage"
        />
      </div>
      <ImageMasonry :images="images" :loading="imageLoading" />
    </section>

    <el-dialog v-model="workDialog" title="编辑作品资料" width="860px">
      <el-form class="form-grid" label-width="92px">
        <el-form-item label="中文名"><el-input v-model="workForm.name" /></el-form-item>
        <el-form-item label="原名"><el-input v-model="workForm.original_name" /></el-form-item>
        <el-form-item label="标语"><el-input v-model="workForm.tagline" /></el-form-item>
        <el-form-item label="状态"><el-input v-model="workForm.status" /></el-form-item>
        <el-form-item label="年份"><el-input-number v-model="workForm.production_year" :min="1900" :max="2100" style="width: 100%" /></el-form-item>
        <el-form-item label="时长"><el-input-number v-model="workForm.run_time_minutes" :min="0" style="width: 100%" /></el-form-item>
        <el-form-item label="评分"><el-input-number v-model="workForm.community_rating" :min="0" :max="10" :step="0.1" style="width: 100%" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="workForm.sort_order" style="width: 100%" /></el-form-item>
        <el-form-item label="内容分级"><el-input v-model="workForm.content_rating" /></el-form-item>
        <el-form-item label="官网"><el-input v-model="workForm.official_site" /></el-form-item>
        <el-form-item label="类型" class="form-grid__wide"><el-input v-model="workForm.genres" placeholder="多个类型可用 / 或 、 分隔" /></el-form-item>
        <el-form-item label="制作" class="form-grid__wide"><el-input v-model="workForm.studios" placeholder="多个制作公司可用 / 或 、 分隔" /></el-form-item>
        <el-form-item label="别名" class="form-grid__wide"><el-input v-model="workForm.aliases" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="简介" class="form-grid__wide"><el-input v-model="workForm.description" type="textarea" :rows="5" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="workDialog = false">取消</el-button>
        <el-button type="primary" :loading="workSaving" @click="saveWork">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="characterDialog" title="创建角色" width="620px">
      <el-form label-width="92px">
        <el-form-item label="中文名">
          <el-input v-model="characterForm.name" />
        </el-form-item>
        <el-form-item label="原名">
          <el-input v-model="characterForm.original_name" />
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="characterForm.aliases" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="characterForm.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="头像">
          <div class="avatar-editor">
            <img v-if="currentCharacterAvatar" :src="currentCharacterAvatar" alt="" class="avatar-preview" />
            <div v-else class="avatar-preview"></div>
            <div class="avatar-controls">
              <el-select v-model="characterForm.avatar_image_id" clearable filterable placeholder="选择已上传图片" style="width: 100%">
                <el-option
                  v-for="image in avatarImages"
                  :key="image.id"
                  :label="avatarImageOptionLabel(image)"
                  :value="image.id"
                />
              </el-select>
              <el-upload :accept="imageUploadAccept" :show-file-list="false" :http-request="uploadCharacterAvatar">
                <el-button :icon="UploadFilled" :loading="uploadingAvatar">上传头像</el-button>
              </el-upload>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="characterDialog = false">取消</el-button>
        <el-button type="primary" :loading="characterSaving" @click="saveCharacter">保存角色</el-button>
      </template>
    </el-dialog>
  </div>
</template>
