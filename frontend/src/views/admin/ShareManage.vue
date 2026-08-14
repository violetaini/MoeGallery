<script setup>
import { computed, onMounted, ref } from 'vue'
import { Delete, DocumentCopy, EditPen, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { mediaUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'
import { sharePageUrl } from '../../utils/shareFormats'

const shares = ref([])
const loading = ref(false)
const editVisible = ref(false)
const editSaving = ref(false)
const editingShare = ref(null)
const editTitle = ref('')
const editExpiresInHours = ref(0)
const previewVisible = ref(false)
const previewShare = ref(null)
const previewPage = ref(1)
const previewPageSize = 12

const expiryOptions = [
  { label: '永久有效', value: 0 },
  { label: '1 天', value: 24 },
  { label: '7 天', value: 168 },
  { label: '30 天', value: 720 }
]

const previewImages = computed(() => {
  const images = previewShare.value?.images || []
  const start = (previewPage.value - 1) * previewPageSize
  return images.slice(start, start + previewPageSize)
})

function linkFor(share) {
  return sharePageUrl(share.token)
}

function displayTitle(share) {
  return /^\d+\s*张图片分享$/.test(share.title) ? '图片分享' : share.title
}

function isExpired(share) {
  if (!share.expires_at) return false
  const expiresAt = new Date(share.expires_at).getTime()
  return Number.isFinite(expiresAt) && expiresAt <= Date.now()
}

function isUsable(share) {
  return share.is_active && !isExpired(share)
}

function statusLabel(share) {
  return isUsable(share) ? '有效' : share.is_active ? '已过期' : '已撤销'
}

function statusType(share) {
  return isUsable(share) ? 'success' : share.is_active ? 'warning' : 'info'
}

function expiryLabel(share) {
  if (!share.expires_at) return '永久有效'
  const label = new Date(share.expires_at).toLocaleString()
  return isExpired(share) ? `已于 ${label} 过期` : `有效至 ${label}`
}

function expiryValueForEdit(share) {
  if (!share.expires_at) return 0
  const hoursLeft = Math.max(0, Math.ceil((new Date(share.expires_at).getTime() - Date.now()) / 3_600_000))
  if (hoursLeft <= 24) return 24
  if (hoursLeft <= 168) return 168
  if (hoursLeft <= 720) return 720
  return 0
}

async function copy(share) {
  try {
    await navigator.clipboard.writeText(linkFor(share))
    ElMessage.success('已复制分享链接')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function load() {
  loading.value = true
  try {
    const data = await galleryApi.shares({ page_size: 100 })
    shares.value = data.items
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载分享记录失败')
  } finally {
    loading.value = false
  }
}

function openEdit(share) {
  editingShare.value = share
  editTitle.value = displayTitle(share)
  editExpiresInHours.value = expiryValueForEdit(share)
  editVisible.value = true
}

function openPreview(share) {
  previewShare.value = share
  previewPage.value = 1
  previewVisible.value = true
}

async function saveEdit() {
  if (!editingShare.value) return
  const title = editTitle.value.trim()
  if (!title) {
    ElMessage.warning('请输入分享标题')
    return
  }
  editSaving.value = true
  try {
    await galleryApi.updateShare(editingShare.value.id, {
      title,
      expires_in_hours: editExpiresInHours.value || null
    })
    ElMessage.success('分享已更新')
    editVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '更新分享失败')
  } finally {
    editSaving.value = false
  }
}

async function revoke(share) {
  const confirmed = await ElMessageBox.confirm(
    `撤销“${displayTitle(share)}”的分享链接？已复制的页面与嵌入代码会立即失效。`,
    '确认撤销分享',
    { type: 'warning' }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  try {
    await galleryApi.revokeShare(share.id)
    ElMessage.success('分享已撤销')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '撤销分享失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="share-manage-page">
    <section class="share-manage-hero">
      <div>
        <p class="share-manage-eyebrow">SHARE CONTROL</p>
        <h2>分享管理</h2>
        <p class="muted">集中管理已创建的分享：复制链接、修改标题和有效期，或随时撤销访问权限。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </section>

    <div v-loading="loading" class="share-manage-content">
      <el-empty v-if="!loading && !shares.length" description="还没有创建分享" />
      <div v-else class="share-manage-grid">
        <article
          v-for="share in shares"
          :key="share.id"
          class="share-manage-card"
          :class="{ 'is-inactive': !isUsable(share) }"
        >
          <header class="share-manage-card__header">
            <div>
              <p class="share-manage-card__label">分享链接</p>
              <h3 :title="displayTitle(share)">{{ displayTitle(share) }}</h3>
            </div>
            <el-tag round :type="statusType(share)">{{ statusLabel(share) }}</el-tag>
          </header>

          <dl class="share-manage-card__meta">
            <div>
              <dt>创建时间</dt>
              <dd>{{ new Date(share.created_at).toLocaleString() }}</dd>
            </div>
            <div>
              <dt>有效期</dt>
              <dd>{{ expiryLabel(share) }}</dd>
            </div>
          </dl>

          <button
            class="share-manage-preview"
            type="button"
            :aria-label="`查看“${displayTitle(share)}”包含的图片`"
            @click="openPreview(share)"
          >
            <img
              v-for="image in share.images.slice(0, 4)"
              :key="image.id"
              :src="mediaUrl(image, 'thumbnail')"
              :alt="image.original_filename || '分享图片'"
              loading="lazy"
            />
            <span>查看所含图片</span>
          </button>

          <div class="share-manage-card__actions">
            <el-button :icon="DocumentCopy" :disabled="!isUsable(share)" @click="copy(share)">复制</el-button>
            <el-button type="danger" plain :icon="Delete" :disabled="!share.is_active" @click="revoke(share)">撤销</el-button>
            <el-button :icon="EditPen" :disabled="!share.is_active" @click="openEdit(share)">修改</el-button>
          </div>
        </article>
      </div>
    </div>

    <el-dialog v-model="editVisible" title="修改分享" width="420px" destroy-on-close>
      <el-form label-position="top" @submit.prevent="saveEdit">
        <el-form-item label="分享标题">
          <el-input v-model="editTitle" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="有效期">
          <el-select v-model="editExpiresInHours" style="width: 100%">
            <el-option v-for="option in expiryOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <p class="share-manage-edit-hint">保存后，有效期将从当前时间重新计算；设置为永久有效可取消到期时间。</p>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存修改</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewVisible"
      class="share-manage-detail-dialog"
      :title="previewShare ? displayTitle(previewShare) : '分享图片'"
      width="min(860px, calc(100vw - 32px))"
      destroy-on-close
    >
      <p class="share-manage-detail-hint">以下为这条分享包含的图片；点击缩略图可打开图片详情。</p>
      <div class="share-manage-detail-grid">
        <a
          v-for="image in previewImages"
          :key="image.id"
          :href="`/images/${image.id}`"
          target="_blank"
          rel="noreferrer"
          :title="image.original_filename || image.filename || '打开图片详情'"
        >
          <img :src="mediaUrl(image, 'preview')" :alt="image.original_filename || '分享图片'" loading="lazy" />
        </a>
      </div>
      <el-pagination
        v-if="(previewShare?.images?.length || 0) > previewPageSize"
        v-model:current-page="previewPage"
        class="share-manage-detail-pagination"
        background
        layout="prev, pager, next"
        :page-size="previewPageSize"
        :total="previewShare?.images?.length || 0"
      />
    </el-dialog>
  </div>
</template>
