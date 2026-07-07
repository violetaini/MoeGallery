<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Search } from '@element-plus/icons-vue'
import { storageUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import AdminImageEditOverlay from '../../components/AdminImageEditOverlay.vue'
import AdminImageWall from '../../components/AdminImageWall.vue'
import { orientationLabel, orientationOptions } from '../../constants/orientations'
import { ratingOptions } from '../../constants/ratings'
import { getImageManageViewMode, normalizeImageManageViewMode, setImageManageViewMode } from '../../utils/adminPreferences'
import { displayId } from '../../utils/displayId'

const tableRef = ref()
const images = ref([])
const works = ref([])
const characters = ref([])
const total = ref(0)
const loading = ref(false)
const batchDialog = ref(false)
const batchSaving = ref(false)
const currentImage = ref(null)
const selectedRows = ref([])
const viewMode = ref(getImageManageViewMode())
const q = ref('')
const page = ref(1)
const pageSize = ref(50)
const pageSizeOptions = [20, 50, 100]
const filters = reactive({
  work_id: undefined,
  character_id: undefined,
  rating: undefined,
  orientation: undefined
})
const batchForm = reactive({
  artist_name: '',
  source_url: '',
  rating: 'safe',
  favorite_count: 0,
  work_ids: [],
  character_ids: []
})
const batchEnabled = reactive({
  artist_name: false,
  source_url: false,
  rating: false,
  favorite_count: false,
  work_ids: false,
  character_ids: false
})
const batchFieldKeys = [
  'artist_name',
  'source_url',
  'rating',
  'favorite_count',
  'work_ids',
  'character_ids'
]

const selectedCount = computed(() => selectedRows.value.length)
const isWaterfallView = computed(() => viewMode.value === 'waterfall')
const selectedImageIds = computed(() => selectedRows.value.map((row) => row.id))

function imageLabel(row) {
  const rowIndex = images.value.findIndex((item) => item.id === row.id)
  const currentDisplayId = displayId(rowIndex, page.value, pageSize.value)
  const name = row.original_filename || row.filename
  return name ? `序号 ${currentDisplayId}（${name}）` : `序号 ${currentDisplayId}`
}

function imageThumb(row) {
  return storageUrl(row.thumbnail_path || row.preview_path || row.file_path)
}

function clearSelection() {
  selectedRows.value = []
  tableRef.value?.clearSelection?.()
}

function selectCurrentPage() {
  selectedRows.value = [...images.value]
  if (!isWaterfallView.value) {
    tableRef.value?.clearSelection?.()
    images.value.forEach((row) => tableRef.value?.toggleRowSelection?.(row, true))
  }
}

function applyRowToForm(row, target) {
  Object.assign(target, {
    artist_name: row.artist_name || '',
    source_url: row.source_url || '',
    rating: row.rating || 'safe',
    favorite_count: row.favorite_count ?? 0,
    work_ids: (row.works || []).map((item) => item.id),
    character_ids: (row.characters || []).map((item) => item.id)
  })
}

function resetBatchFlags() {
  for (const key of batchFieldKeys) {
    batchEnabled[key] = false
  }
}

function openBatchDialog() {
  if (!selectedRows.value.length) {
    return
  }
  applyRowToForm(selectedRows.value[0], batchForm)
  resetBatchFlags()
  batchDialog.value = true
}

async function loadOptions() {
  const [workData, characterData] = await Promise.all([
    galleryApi.works({ page_size: 100 }),
    galleryApi.characters({ page_size: 100 })
  ])
  works.value = workData.items
  characters.value = characterData.items
}

async function loadAdminSettings() {
  try {
    const data = await galleryApi.settings()
    viewMode.value = normalizeImageManageViewMode(data.image_manage_view_mode)
    setImageManageViewMode(viewMode.value)
  } catch (error) {
    viewMode.value = getImageManageViewMode()
  }
}

async function load() {
  loading.value = true
  try {
    const data = await galleryApi.images({
      page: page.value,
      page_size: pageSize.value,
      q: q.value,
      public_only: false,
      exclude_cover_images: true,
      exclude_avatar_images: true,
      ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== undefined))
    })
    images.value = data.items
    total.value = data.total
    await nextTick()
    clearSelection()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载图片失败')
  } finally {
    loading.value = false
  }
}

function reloadFromFirstPage() {
  page.value = 1
  load()
}

function resetFilters() {
  q.value = ''
  filters.work_id = undefined
  filters.character_id = undefined
  filters.rating = undefined
  filters.orientation = undefined
  reloadFromFirstPage()
}

function handleSelectionChange(rows) {
  selectedRows.value = rows
}

function toggleWallSelection(row, checked) {
  if (checked) {
    if (!selectedRows.value.some((item) => item.id === row.id)) {
      selectedRows.value = [...selectedRows.value, row]
    }
    return
  }
  selectedRows.value = selectedRows.value.filter((item) => item.id !== row.id)
}

function changePage(current) {
  page.value = current
  load()
}

function changePageSize(size) {
  pageSize.value = size
  page.value = 1
  load()
}

function edit(row) {
  currentImage.value = row
}

function closeEditor() {
  currentImage.value = null
}

async function handleEditorSaved() {
  currentImage.value = null
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`删除图片 ${imageLabel(row)}？`, '确认删除', { type: 'warning' })
  try {
    await galleryApi.deleteImage(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '删除失败')
  }
}

function buildBatchUpdate() {
  const update = {}
  for (const key of batchFieldKeys) {
    if (batchEnabled[key]) {
      update[key] = batchForm[key]
    }
  }
  return update
}

async function saveBatch() {
  const update = buildBatchUpdate()
  if (!Object.keys(update).length) {
    ElMessage.warning('至少选择一个要批量修改的字段')
    return
  }
  batchSaving.value = true
  try {
    const result = await galleryApi.updateImagesBatch({
      image_ids: selectedRows.value.map((row) => row.id),
      update
    })
    ElMessage.success(`已批量更新 ${result.count} 张图片`)
    batchDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '批量保存失败')
  } finally {
    batchSaving.value = false
  }
}

async function removeSelected() {
  if (!selectedRows.value.length) {
    return
  }
  await ElMessageBox.confirm(`删除选中的 ${selectedRows.value.length} 张图片？`, '确认批量删除', { type: 'warning' })
  try {
    const result = await galleryApi.deleteImagesBatch({
      image_ids: selectedRows.value.map((row) => row.id)
    })
    ElMessage.success(`已删除 ${result.count} 张图片`)
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '批量删除失败')
  }
}

onMounted(async () => {
  await Promise.all([loadAdminSettings(), loadOptions()])
  await load()
})
</script>

<template>
  <div class="admin-card">
    <div class="admin-toolbar">
      <el-input v-model="q" clearable placeholder="搜索图片" :prefix-icon="Search" style="width: 220px" @keyup.enter="reloadFromFirstPage" />
      <el-select v-model="filters.work_id" clearable filterable placeholder="作品" style="width: 190px" @change="reloadFromFirstPage">
        <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
      </el-select>
      <el-select v-model="filters.character_id" clearable filterable placeholder="角色" style="width: 190px" @change="reloadFromFirstPage">
        <el-option v-for="character in characters" :key="character.id" :label="character.name" :value="character.id" />
      </el-select>
      <el-select v-model="filters.rating" clearable placeholder="分级" style="width: 190px" @change="reloadFromFirstPage">
        <el-option v-for="rating in ratingOptions" :key="rating.value" :label="rating.label" :value="rating.value" />
      </el-select>
      <el-select v-model="filters.orientation" clearable placeholder="方向" style="width: 150px" @change="reloadFromFirstPage">
        <el-option v-for="orientation in orientationOptions" :key="orientation.value" :label="orientation.label" :value="orientation.value" />
      </el-select>
      <el-button @click="reloadFromFirstPage">搜索</el-button>
      <el-button @click="resetFilters">重置</el-button>
      <el-button v-if="isWaterfallView" @click="selectCurrentPage">全选本页</el-button>
      <el-button type="primary" @click="$router.push('/admin/images/upload')">上传图片</el-button>
    </div>

    <div v-if="selectedCount" class="admin-batch-bar">
      <div class="muted">已选择 {{ selectedCount }} 张图片</div>
      <div class="admin-batch-actions">
        <el-button type="primary" @click="openBatchDialog">批量编辑</el-button>
        <el-button type="danger" :icon="Delete" @click="removeSelected">批量删除</el-button>
        <el-button @click="selectCurrentPage">全选本页</el-button>
        <el-button @click="clearSelection">清空选择</el-button>
      </div>
    </div>

    <AdminImageWall
      v-if="isWaterfallView"
      v-loading="loading"
      :images="images"
      :loading="loading"
      :selected-ids="selectedImageIds"
      @edit="edit"
      @toggle-selection="toggleWallSelection"
    />

    <el-table
      v-else
      ref="tableRef"
      v-loading="loading"
      :data="images"
      row-key="id"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column label="预览" width="92">
        <template #default="{ row }">
          <el-image
            class="admin-image-thumb"
            :src="imageThumb(row)"
            fit="cover"
            @click="edit(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="序号" width="80">
        <template #default="{ $index }">{{ displayId($index, page, pageSize) }}</template>
      </el-table-column>
      <el-table-column label="文件" min-width="190">
        <template #default="{ row }">
          <strong>{{ row.original_filename || row.filename }}</strong>
          <div class="muted">{{ row.width }} x {{ row.height }} · {{ orientationLabel(row.orientation) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="作品" min-width="160">
        <template #default="{ row }">{{ row.works.map((item) => item.name).join('、') || '-' }}</template>
      </el-table-column>
      <el-table-column label="角色" min-width="160">
        <template #default="{ row }">{{ row.characters.map((item) => item.name).join('、') || '-' }}</template>
      </el-table-column>
      <el-table-column prop="rating" label="分级" width="110" />
      <el-table-column label="公开" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_public ? 'success' : 'info'">{{ row.is_public ? '公开' : '隐藏' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="132" fixed="right">
        <template #default="{ row }">
          <el-tooltip content="修改信息" placement="top">
            <el-button circle :icon="Edit" @click="edit(row)" />
          </el-tooltip>
          <el-tooltip content="删除图片" placement="top">
            <el-button circle type="danger" :icon="Delete" @click="remove(row)" />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <div class="admin-pagination">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="pageSizeOptions"
        :total="total"
        background
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="changePage"
        @size-change="changePageSize"
      />
    </div>

    <el-dialog v-model="batchDialog" title="批量编辑" width="860px" destroy-on-close>
      <div class="batch-form-grid">
        <div class="batch-field">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.artist_name">作者</el-checkbox>
          </div>
          <el-input v-model="batchForm.artist_name" :disabled="!batchEnabled.artist_name" />
        </div>
        <div class="batch-field batch-field--wide">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.source_url">来源</el-checkbox>
          </div>
          <el-input v-model="batchForm.source_url" :disabled="!batchEnabled.source_url" />
        </div>
        <div class="batch-field">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.rating">分级</el-checkbox>
          </div>
          <el-radio-group v-model="batchForm.rating" :disabled="!batchEnabled.rating">
            <el-radio-button label="safe">safe</el-radio-button>
            <el-radio-button label="sensitive">sensitive</el-radio-button>
            <el-radio-button label="hidden">hidden</el-radio-button>
          </el-radio-group>
        </div>
        <div class="batch-field">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.favorite_count">收藏数</el-checkbox>
          </div>
          <el-input-number v-model="batchForm.favorite_count" :min="0" :disabled="!batchEnabled.favorite_count" />
        </div>
        <div class="batch-field batch-field--wide">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.work_ids">作品</el-checkbox>
          </div>
          <el-select v-model="batchForm.work_ids" multiple filterable clearable style="width: 100%" :disabled="!batchEnabled.work_ids">
            <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
          </el-select>
        </div>
        <div class="batch-field batch-field--wide">
          <div class="batch-field__head">
            <el-checkbox v-model="batchEnabled.character_ids">角色</el-checkbox>
          </div>
          <el-select v-model="batchForm.character_ids" multiple filterable clearable style="width: 100%" :disabled="!batchEnabled.character_ids">
            <el-option v-for="character in characters" :key="character.id" :label="character.name" :value="character.id" />
          </el-select>
        </div>
      </div>
      <template #footer>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" :loading="batchSaving" @click="saveBatch">保存</el-button>
      </template>
    </el-dialog>

    <AdminImageEditOverlay
      v-if="currentImage"
      :image="currentImage"
      @close="closeEditor"
      @saved="handleEditorSaved"
    />
  </div>
</template>
