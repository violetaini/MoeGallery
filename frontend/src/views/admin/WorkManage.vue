<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import { storageUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import { imageUploadAccept } from '../../constants/uploadFormats'
import { displayId } from '../../utils/displayId'

const works = ref([])
const mediaImages = ref([])
const total = ref(0)
const router = useRouter()
const q = ref('')
const dialog = ref(false)
const loading = ref(false)
const uploadingCover = ref(false)
const uploadingBackdrop = ref(false)
const form = reactive({
  id: null,
  name: '',
  original_name: '',
  aliases: '',
  description: '',
  cover_image_id: null,
  backdrop_image_id: null,
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

const currentCover = computed(() => {
  const selected = mediaImages.value.find((image) => image.id === form.cover_image_id)
  return storageUrl(selected?.thumbnail_path || selected?.preview_path)
})

const currentBackdrop = computed(() => {
  const selected = mediaImages.value.find((image) => image.id === form.backdrop_image_id)
  return storageUrl(selected?.thumbnail_path || selected?.preview_path)
})

const mediaImageDisplayIds = computed(() => new Map(mediaImages.value.map((image, index) => [image.id, displayId(index)])))

function imageOptionLabel(image) {
  return `${image.original_filename || image.filename || '未命名图片'} · 序号 ${mediaImageDisplayIds.value.get(image.id) || '-'}`
}

async function loadOptions() {
  const data = await galleryApi.images({ page_size: 100, public_only: false })
  mediaImages.value = data.items
}

async function load() {
  loading.value = true
  const data = await galleryApi.works({ q: q.value, page_size: 100 })
  works.value = data.items
  total.value = data.total
  loading.value = false
}

function create() {
  Object.assign(form, {
    id: null,
    name: '',
    original_name: '',
    aliases: '',
    description: '',
    cover_image_id: null,
    backdrop_image_id: null,
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
  dialog.value = true
}

function edit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    original_name: row.original_name || '',
    aliases: row.aliases || '',
    description: row.description || '',
    cover_image_id: row.cover_image_id,
    backdrop_image_id: row.backdrop_image_id,
    tagline: row.tagline || '',
    production_year: row.production_year,
    run_time_minutes: row.run_time_minutes,
    community_rating: row.community_rating,
    content_rating: row.content_rating || '',
    genres: row.genres || '',
    studios: row.studios || '',
    official_site: row.official_site || '',
    status: row.status || '',
    sort_order: row.sort_order
  })
  if (row.cover_image && !mediaImages.value.some((image) => image.id === row.cover_image.id)) {
    mediaImages.value.unshift(row.cover_image)
  }
  if (row.backdrop_image && !mediaImages.value.some((image) => image.id === row.backdrop_image.id)) {
    mediaImages.value.unshift(row.backdrop_image)
  }
  dialog.value = true
}

async function uploadWorkImage(upload, target) {
  const loadingRef = target === 'cover' ? uploadingCover : uploadingBackdrop
  loadingRef.value = true
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
      if (target === 'cover') form.cover_image_id = image.id
      else form.backdrop_image_id = image.id
      if (!mediaImages.value.some((item) => item.id === image.id)) {
        mediaImages.value.unshift(image)
      }
      ElMessage.success(target === 'cover' ? '封面已上传' : '背景图已上传')
    }
    upload.onSuccess?.(result)
    return result
  } catch (error) {
    upload.onError?.(error)
    throw error
  } finally {
    loadingRef.value = false
  }
}

function uploadCover(upload) {
  return uploadWorkImage(upload, 'cover')
}

function uploadBackdrop(upload) {
  return uploadWorkImage(upload, 'backdrop')
}

async function save() {
  const payload = {
    ...form,
    cover_image_id: form.cover_image_id || null,
    backdrop_image_id: form.backdrop_image_id || null,
    production_year: form.production_year || null,
    run_time_minutes: form.run_time_minutes || null,
    community_rating: form.community_rating || null
  }
  if (form.id) await galleryApi.updateWork(form.id, payload)
  else await galleryApi.createWork(payload)
  dialog.value = false
  ElMessage.success('已保存')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`删除作品 ${row.name}？`, '确认删除', { type: 'warning' })
  await galleryApi.deleteWork(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  await Promise.all([loadOptions(), load()])
})
</script>

<template>
  <div class="admin-card">
    <div class="admin-toolbar">
      <el-input v-model="q" clearable placeholder="搜索作品" :prefix-icon="Search" style="width: 260px" @keyup.enter="load" />
      <el-button @click="load">搜索</el-button>
      <el-button type="primary" :icon="Plus" @click="create">新增作品</el-button>
      <span class="muted">共 {{ total }} 个</span>
    </div>
    <el-table v-loading="loading" :data="works" row-key="id">
      <el-table-column label="封面" width="92">
        <template #default="{ row }">
          <img
            v-if="row.cover_image"
            :src="storageUrl(row.cover_image.thumbnail_path || row.cover_image.preview_path)"
            alt=""
            class="table-thumb"
          />
          <div v-else class="table-thumb"></div>
        </template>
      </el-table-column>
      <el-table-column label="序号" width="80">
        <template #default="{ $index }">{{ displayId($index) }}</template>
      </el-table-column>
      <el-table-column label="中文名" min-width="180">
        <template #default="{ row }">
          <el-button link type="primary" class="admin-link-button" @click="router.push(`/admin/works/${row.id}`)">
            {{ row.name }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="original_name" label="原名" min-width="180" />
      <el-table-column prop="production_year" label="年份" width="100" />
      <el-table-column prop="community_rating" label="评分" width="100" />
      <el-table-column prop="sort_order" label="排序" width="100" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button circle :icon="Edit" @click="edit(row)" />
          <el-button circle type="danger" :icon="Delete" @click="remove(row)" />
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑作品' : '新增作品'" width="820px">
      <el-form label-width="96px">
        <el-form-item label="中文名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="原名"><el-input v-model="form.original_name" /></el-form-item>
        <el-form-item label="标语"><el-input v-model="form.tagline" /></el-form-item>
        <el-form-item label="别名"><el-input v-model="form.aliases" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="简介"><el-input v-model="form.description" type="textarea" :rows="5" /></el-form-item>
        <el-form-item label="封面">
          <div class="avatar-editor">
            <img v-if="currentCover" :src="currentCover" alt="" class="avatar-preview" />
            <div v-else class="avatar-preview"></div>
            <div class="avatar-controls">
              <el-select v-model="form.cover_image_id" clearable filterable placeholder="选择已上传图片" style="width: 100%">
                <el-option
                  v-for="image in mediaImages"
                  :key="image.id"
                  :label="imageOptionLabel(image)"
                  :value="image.id"
                />
              </el-select>
              <el-upload :accept="imageUploadAccept" :show-file-list="false" :http-request="uploadCover">
                <el-button :icon="UploadFilled" :loading="uploadingCover">上传封面</el-button>
              </el-upload>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="背景图">
          <div class="avatar-editor">
            <img v-if="currentBackdrop" :src="currentBackdrop" alt="" class="avatar-preview" />
            <div v-else class="avatar-preview"></div>
            <div class="avatar-controls">
              <el-select v-model="form.backdrop_image_id" clearable filterable placeholder="选择已上传图片" style="width: 100%">
                <el-option
                  v-for="image in mediaImages"
                  :key="image.id"
                  :label="imageOptionLabel(image)"
                  :value="image.id"
                />
              </el-select>
              <el-upload :accept="imageUploadAccept" :show-file-list="false" :http-request="uploadBackdrop">
                <el-button :icon="UploadFilled" :loading="uploadingBackdrop">上传背景图</el-button>
              </el-upload>
            </div>
          </div>
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="年份"><el-input-number v-model="form.production_year" :min="1900" :max="2100" /></el-form-item>
          <el-form-item label="运行时"><el-input-number v-model="form.run_time_minutes" :min="0" /></el-form-item>
          <el-form-item label="评分"><el-input-number v-model="form.community_rating" :min="0" :max="10" :step="0.1" /></el-form-item>
          <el-form-item label="分级"><el-input v-model="form.content_rating" /></el-form-item>
        </div>
        <el-form-item label="类型"><el-input v-model="form.genres" placeholder="多个类型用顿号或逗号分隔" /></el-form-item>
        <el-form-item label="制作方"><el-input v-model="form.studios" /></el-form-item>
        <el-form-item label="官网"><el-input v-model="form.official_site" /></el-form-item>
        <el-form-item label="状态"><el-input v-model="form.status" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="form.sort_order" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
