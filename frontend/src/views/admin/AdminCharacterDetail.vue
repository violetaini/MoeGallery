<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, UploadFilled } from '@element-plus/icons-vue'
import { galleryApi } from '../../api/gallery'
import ImageMasonry from '../../components/ImageMasonry.vue'
import ResponsiveImage from '../../components/ResponsiveImage.vue'
import { imageUploadAccept } from '../../constants/uploadFormats'

const route = useRoute()
const router = useRouter()
const character = ref(null)
const images = ref([])
const imageTotal = ref(0)
const imagePage = ref(1)
const imagePageSize = 24
const pageLoading = ref(false)
const imageLoading = ref(false)
const uploading = ref(false)
const characterDialog = ref(false)
const characterSaving = ref(false)
const uploadFiles = ref([])
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
  description: ''
})

const characterId = computed(() => Number(route.params.id))
const sourceWorkId = computed(() => {
  const value = Number(route.query.fromWork)
  return Number.isFinite(value) && value > 0 ? value : null
})
const backButtonLabel = computed(() => (sourceWorkId.value ? '返回作品管理' : '返回角色管理'))
const backTarget = computed(() => (sourceWorkId.value ? `/admin/works/${sourceWorkId.value}` : '/admin/characters'))

async function loadCharacter() {
  pageLoading.value = true
  try {
    character.value = await galleryApi.character(characterId.value)
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
      character_id: characterId.value
    })
    images.value = data.items
    imageTotal.value = data.total
  } finally {
    imageLoading.value = false
  }
}

function changeImagePage(nextPage) {
  imagePage.value = nextPage
  loadImages()
}

function openEditCharacter() {
  if (!character.value) return
  Object.assign(characterForm, {
    name: character.value.name || '',
    original_name: character.value.original_name || '',
    aliases: character.value.aliases || '',
    description: character.value.description || ''
  })
  characterDialog.value = true
}

async function saveCharacter() {
  if (!characterForm.name.trim()) {
    ElMessage.warning('请填写角色名')
    return
  }
  characterSaving.value = true
  try {
    await galleryApi.updateCharacter(characterId.value, {
      name: characterForm.name.trim(),
      original_name: characterForm.original_name,
      aliases: characterForm.aliases,
      description: characterForm.description
    })
    characterDialog.value = false
    ElMessage.success('角色资料已保存')
    await loadCharacter()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存角色失败')
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
  data.append('work_ids', character.value?.work_id ? String(character.value.work_id) : '')
  data.append('character_ids', String(characterId.value))
  data.append('rating', uploadForm.rating)
  data.append('is_public', String(uploadForm.is_public))
  if (uploadForm.source_url) data.append('source_url', uploadForm.source_url)
  if (uploadForm.artist_name) data.append('artist_name', uploadForm.artist_name)
  try {
    const result = await galleryApi.uploadImages(data)
    ElMessage.success(`已上传 ${result.items.length} 张图片`)
    uploadFiles.value = []
    await Promise.all([loadCharacter(), loadImages()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '上传失败')
    throw error
  } finally {
    uploading.value = false
  }
}

watch(characterId, async () => {
  if (!Number.isFinite(characterId.value) || characterId.value <= 0) return
  imagePage.value = 1
  await Promise.all([loadCharacter(), loadImages()])
}, { immediate: true })
</script>

<template>
  <el-skeleton v-if="pageLoading && !character" :rows="8" animated />
  <div v-else-if="character" class="admin-detail-page">
    <div class="admin-detail-topbar">
      <el-button :icon="ArrowLeft" @click="router.push(backTarget)">{{ backButtonLabel }}</el-button>
    </div>

    <section class="profile-head">
      <ResponsiveImage
        v-if="character.avatar_image"
        :image="character.avatar_image"
        :alt="character.name"
        img-class="cover-image"
        variant="preview"
        prefer-hdr
        prefer-animated
      />
      <div v-else class="cover-image"></div>
      <div>
        <h1>{{ character.name }}</h1>
        <p class="muted">
          <RouterLink v-if="character.work" :to="`/admin/works/${character.work.id}`">{{ character.work.name }}</RouterLink>
          <span v-if="character.original_name"> · {{ character.original_name }}</span>
        </p>
        <p>{{ character.description || '暂无简介' }}</p>
        <div class="chip-row">
          <el-tag type="success">自动附带作品：{{ character.work?.name || '无' }}</el-tag>
          <el-tag type="warning">自动附带角色：{{ character.name }}</el-tag>
          <el-button type="primary" :icon="Edit" @click="openEditCharacter">编辑资料</el-button>
        </div>
      </div>
    </section>

    <section class="media-section admin-detail-upload-panel">
      <div class="section-title media-section-title">
        <div>
          <h2>上传图片</h2>
          <span class="muted">这里上传会自动绑定当前作品和当前角色，不需要重复填写。</span>
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
            <el-button type="primary" :loading="uploading" :disabled="!uploadFiles.length" @click="submitUpload">上传到当前角色</el-button>
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

    <el-dialog v-model="characterDialog" title="编辑角色资料" width="680px">
      <el-form label-width="92px">
        <el-form-item label="中文名"><el-input v-model="characterForm.name" /></el-form-item>
        <el-form-item label="原名"><el-input v-model="characterForm.original_name" /></el-form-item>
        <el-form-item label="别名"><el-input v-model="characterForm.aliases" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="简介"><el-input v-model="characterForm.description" type="textarea" :rows="5" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="characterDialog = false">取消</el-button>
        <el-button type="primary" :loading="characterSaving" @click="saveCharacter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
