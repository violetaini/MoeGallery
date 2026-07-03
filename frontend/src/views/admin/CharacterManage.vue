<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import { storageUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import { imageUploadAccept } from '../../constants/uploadFormats'
import { displayId } from '../../utils/displayId'

const characters = ref([])
const works = ref([])
const avatarImages = ref([])
const router = useRouter()
const q = ref('')
const workId = ref()
const dialog = ref(false)
const loading = ref(false)
const uploadingAvatar = ref(false)
const form = reactive({
  id: null,
  work_id: null,
  name: '',
  original_name: '',
  aliases: '',
  description: '',
  avatar_image_id: null
})

const currentAvatar = computed(() => {
  const selected = avatarImages.value.find((image) => image.id === form.avatar_image_id)
  return storageUrl(selected?.thumbnail_path || selected?.preview_path)
})

const avatarImageDisplayIds = computed(() => new Map(avatarImages.value.map((image, index) => [image.id, displayId(index)])))

function imageOptionLabel(image) {
  return `${image.original_filename || image.filename || '未命名图片'} · 序号 ${avatarImageDisplayIds.value.get(image.id) || '-'}`
}

async function loadOptions() {
  const [workData, imageData] = await Promise.all([
    galleryApi.works({ page_size: 100 }),
    galleryApi.images({ page_size: 100, public_only: false })
  ])
  works.value = workData.items
  avatarImages.value = imageData.items
}

async function load() {
  loading.value = true
  const data = await galleryApi.characters({ q: q.value, work_id: workId.value, page_size: 100 })
  characters.value = data.items
  loading.value = false
}

function create() {
  Object.assign(form, {
    id: null,
    work_id: works.value[0]?.id || null,
    name: '',
    original_name: '',
    aliases: '',
    description: '',
    avatar_image_id: null
  })
  dialog.value = true
}

function edit(row) {
  Object.assign(form, {
    id: row.id,
    work_id: row.work_id,
    name: row.name,
    original_name: row.original_name || '',
    aliases: row.aliases || '',
    description: row.description || '',
    avatar_image_id: row.avatar_image_id
  })
  if (row.avatar_image && !avatarImages.value.some((image) => image.id === row.avatar_image.id)) {
    avatarImages.value.unshift(row.avatar_image)
  }
  dialog.value = true
}

async function uploadAvatar(upload) {
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
      form.avatar_image_id = image.id
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

async function save() {
  const payload = { ...form, avatar_image_id: form.avatar_image_id || null }
  if (form.id) await galleryApi.updateCharacter(form.id, payload)
  else await galleryApi.createCharacter(payload)
  dialog.value = false
  ElMessage.success('已保存')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`删除角色 ${row.name}？`, '确认删除', { type: 'warning' })
  await galleryApi.deleteCharacter(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  await loadOptions()
  await load()
})
</script>

<template>
  <div class="admin-card">
    <div class="admin-toolbar">
      <el-input v-model="q" clearable placeholder="搜索角色" :prefix-icon="Search" style="width: 220px" @keyup.enter="load" />
      <el-select v-model="workId" clearable filterable placeholder="作品" style="width: 220px" @change="load">
        <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
      </el-select>
      <el-button @click="load">搜索</el-button>
      <el-button type="primary" :icon="Plus" @click="create">新增角色</el-button>
    </div>
    <el-table v-loading="loading" :data="characters" row-key="id">
      <el-table-column label="头像" width="92">
        <template #default="{ row }">
          <img
            v-if="row.avatar_image"
            :src="storageUrl(row.avatar_image.thumbnail_path || row.avatar_image.preview_path)"
            alt=""
            class="table-thumb"
          />
          <div v-else class="table-thumb"></div>
        </template>
      </el-table-column>
      <el-table-column label="序号" width="80">
        <template #default="{ $index }">{{ displayId($index) }}</template>
      </el-table-column>
      <el-table-column label="中文名" min-width="160">
        <template #default="{ row }">
          <el-button link type="primary" class="admin-link-button" @click="router.push(`/admin/characters/${row.id}`)">
            {{ row.name }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="original_name" label="原名" min-width="160" />
      <el-table-column label="作品" min-width="160">
        <template #default="{ row }">
          <el-button
            v-if="row.work"
            link
            type="primary"
            class="admin-link-button"
            @click="router.push(`/admin/works/${row.work.id}`)"
          >
            {{ row.work.name }}
          </el-button>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button circle :icon="Edit" @click="edit(row)" />
          <el-button circle type="danger" :icon="Delete" @click="remove(row)" />
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑角色' : '新增角色'" width="680px">
      <el-form label-width="96px">
        <el-form-item label="所属作品">
          <el-select v-model="form.work_id" filterable style="width: 100%">
            <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="中文名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="原名"><el-input v-model="form.original_name" /></el-form-item>
        <el-form-item label="别名"><el-input v-model="form.aliases" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="简介"><el-input v-model="form.description" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="头像">
          <div class="avatar-editor">
            <img v-if="currentAvatar" :src="currentAvatar" alt="" class="avatar-preview" />
            <div v-else class="avatar-preview"></div>
            <div class="avatar-controls">
              <el-select v-model="form.avatar_image_id" clearable filterable placeholder="选择已上传图片" style="width: 100%">
                <el-option
                  v-for="image in avatarImages"
                  :key="image.id"
                  :label="imageOptionLabel(image)"
                  :value="image.id"
                />
              </el-select>
              <el-upload :accept="imageUploadAccept" :show-file-list="false" :http-request="uploadAvatar">
                <el-button :icon="UploadFilled" :loading="uploadingAvatar">上传头像</el-button>
              </el-upload>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
