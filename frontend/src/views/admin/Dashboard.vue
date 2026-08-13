<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Picture, Upload, User } from '@element-plus/icons-vue'
import { mediaUrl } from '../../api/client'
import { galleryApi } from '../../api/gallery'

const stats = ref(null)
const recentImages = ref([])
const loading = ref(false)
const loadError = ref('')

function imageTitle(image) {
  return image.original_filename || image.filename || '图片'
}

function uploadedDate(image) {
  if (!image.created_at) return '刚刚上传'
  return new Date(image.created_at).toLocaleDateString()
}

function formatBytes(value) {
  const size = Number(value || 0)
  if (size >= 1024 * 1024 * 1024) return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

onMounted(async () => {
  loading.value = true
  loadError.value = ''
  const [statsResult, imagesResult] = await Promise.allSettled([
    galleryApi.stats(),
    galleryApi.images({
      page_size: 12,
      public_only: false,
      exclude_cover_images: true,
      exclude_backdrop_images: true,
      exclude_avatar_images: true
    })
  ])
  if (statsResult.status === 'fulfilled') stats.value = statsResult.value
  if (imagesResult.status === 'fulfilled') recentImages.value = imagesResult.value.items
  const failures = [statsResult, imagesResult].filter((result) => result.status === 'rejected')
  if (failures.length) {
    loadError.value = '部分首页数据加载失败，请稍后刷新'
    ElMessage.error(failures[0].reason?.response?.data?.detail || loadError.value)
  }
  loading.value = false
})
</script>

<template>
  <div v-loading="loading" class="admin-dashboard">
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" />
    <section class="admin-dashboard__section">
      <div class="admin-dashboard__section-title">
        <h3>快捷操作</h3>
      </div>
      <div class="admin-quick-grid">
        <RouterLink class="admin-quick-card" to="/admin/images/upload">
          <el-icon><Upload /></el-icon>
          <strong>上传图片</strong>
          <span class="muted">批量录入新图并写入作品/角色关系</span>
        </RouterLink>
        <RouterLink class="admin-quick-card" to="/admin/images">
          <el-icon><Picture /></el-icon>
          <strong>图片管理</strong>
          <span class="muted">预览、筛选、批量编辑和删除</span>
        </RouterLink>
        <RouterLink class="admin-quick-card" to="/admin/works">
          <el-icon><FolderOpened /></el-icon>
          <strong>作品管理</strong>
          <span class="muted">维护封面、背景图、角色和作品资料</span>
        </RouterLink>
        <RouterLink class="admin-quick-card" to="/admin/characters">
          <el-icon><User /></el-icon>
          <strong>角色管理</strong>
          <span class="muted">维护角色头像、简介和关联图片</span>
        </RouterLink>
      </div>
    </section>
    <section v-if="stats" class="admin-dashboard__section">
      <div class="admin-dashboard__section-title">
        <h3>数据统计</h3>
      </div>
      <div class="stats-grid">
        <div class="stat-card">
          <span class="muted">全部图片</span>
          <strong>{{ stats.image_count }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">公开图片</span>
          <strong>{{ stats.public_image_count }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">作品数量</span>
          <strong>{{ stats.work_count }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">角色数量</span>
          <strong>{{ stats.character_count }}</strong>
        </div>
        <div class="stat-card">
          <span class="muted">文件占用</span>
          <strong>{{ formatBytes(stats.total_file_size) }}</strong>
        </div>
      </div>
    </section>
    <section v-if="recentImages.length" class="admin-recent-strip">
      <div class="admin-dashboard__section-title">
        <h3>最近上传</h3>
        <RouterLink class="admin-link-button" to="/admin/images">进入图片管理</RouterLink>
      </div>
      <div class="admin-recent-strip__rail">
        <RouterLink
          v-for="image in recentImages"
          :key="image.id"
          class="admin-recent-strip__item"
          to="/admin/images"
        >
          <img
            :src="mediaUrl(image, 'thumbnail')"
            :alt="imageTitle(image)"
          />
          <span class="admin-recent-strip__shade"></span>
          <span class="admin-recent-strip__meta">
            <strong>{{ imageTitle(image) }}</strong>
            <span>
              <em>{{ uploadedDate(image) }}</em>
              <b>{{ image.is_public ? '公开' : '私有' }}</b>
            </span>
          </span>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
