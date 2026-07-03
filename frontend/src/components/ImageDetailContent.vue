<script setup>
import { computed, ref, watch } from 'vue'
import { Link, Star, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { galleryApi } from '../api/gallery'
import ResponsiveImage from './ResponsiveImage.vue'
import { ratingLabel, ratingTagType } from '../constants/ratings'
import { isImageFavorited, setImageFavorited } from '../utils/favorites'

const props = defineProps({
  image: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['updated'])
const favoriteLoading = ref(false)
const favorited = ref(false)

const title = computed(() => props.image?.original_filename || props.image?.filename || '图片')
const dynamicRangeLabel = computed(() => {
  if (props.image?.dynamic_range === 'hdr') return 'HDR'
  return 'SDR'
})
const bitDepthLabel = computed(() => {
  const value = Number(props.image?.bit_depth || 0)
  return value > 0 ? `${value}-bit` : '-'
})
const colorProfileLabel = computed(() => props.image?.color_profile || '-')

watch(() => props.image?.id, (id) => {
  favorited.value = id ? isImageFavorited(id) : false
}, { immediate: true })

async function toggleFavorite() {
  if (!props.image?.id || favoriteLoading.value) {
    return
  }
  favoriteLoading.value = true
  try {
    const nextFavorited = !favorited.value
    const updated = nextFavorited
      ? await galleryApi.favoriteImage(props.image.id)
      : await galleryApi.unfavoriteImage(props.image.id)
    favorited.value = nextFavorited
    setImageFavorited(props.image.id, nextFavorited)
    emit('updated', updated)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '收藏操作失败')
  } finally {
    favoriteLoading.value = false
  }
}
</script>

<template>
  <el-skeleton v-if="loading" :rows="8" animated />
  <div v-else-if="image" class="detail-layout image-detail-view">
    <div class="detail-panel">
      <ResponsiveImage
        :image="image"
        :alt="title"
        img-class="detail-image"
        variant="preview"
        prefer-hdr
        prefer-animated
      />
    </div>
    <aside class="detail-panel image-detail-meta">
      <h2>{{ title }}</h2>
      <div class="chip-row">
        <el-tag>{{ image.width }} x {{ image.height }}</el-tag>
        <el-tag type="success">{{ Math.round(image.file_size / 1024) }} KB</el-tag>
        <el-tag :type="ratingTagType(image.rating)">{{ ratingLabel(image.rating) }}</el-tag>
        <el-tag v-if="image.dynamic_range === 'hdr'" type="warning">HDR</el-tag>
        <el-tag v-if="image.is_animated" type="info">动图</el-tag>
      </div>
      <div class="image-detail-actions">
        <el-button :type="favorited ? 'primary' : 'default'" :icon="Star" :loading="favoriteLoading" @click="toggleFavorite">
          {{ favorited ? '已收藏' : '收藏' }}
        </el-button>
        <span class="muted">收藏 {{ image.favorite_count }}</span>
      </div>

      <el-descriptions :column="1" border style="margin-top: 18px">
        <el-descriptions-item label="作者">{{ image.artist_name || '未知' }}</el-descriptions-item>
        <el-descriptions-item label="MIME">{{ image.mime_type }}</el-descriptions-item>
        <el-descriptions-item label="显示">{{ dynamicRangeLabel }}</el-descriptions-item>
        <el-descriptions-item label="位深">{{ bitDepthLabel }}</el-descriptions-item>
        <el-descriptions-item label="色彩">{{ colorProfileLabel }}</el-descriptions-item>
        <el-descriptions-item label="上传时间">{{ new Date(image.created_at).toLocaleString() }}</el-descriptions-item>
        <el-descriptions-item label="浏览">
          <el-icon><View /></el-icon>
          {{ image.view_count }}
        </el-descriptions-item>
        <el-descriptions-item label="收藏">
          <el-icon><Star /></el-icon>
          {{ image.favorite_count }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="section-title">
        <h2>作品</h2>
      </div>
      <div class="chip-row">
        <RouterLink v-for="work in image.works" :key="work.id" :to="`/works/${work.id}`">
          <el-tag effect="dark">{{ work.name }}</el-tag>
        </RouterLink>
        <span v-if="!image.works.length" class="muted">未绑定</span>
      </div>

      <div class="section-title">
        <h2>角色</h2>
      </div>
      <div class="chip-row">
        <RouterLink v-for="character in image.characters" :key="character.id" :to="`/characters/${character.id}`">
          <el-tag type="success">{{ character.name }}</el-tag>
        </RouterLink>
        <span v-if="!image.characters.length" class="muted">未绑定</span>
      </div>

      <div class="section-title">
        <h2>分级</h2>
      </div>
      <div class="chip-row">
        <el-tag :type="ratingTagType(image.rating)">{{ ratingLabel(image.rating) }}</el-tag>
      </div>

      <el-button v-if="image.source_url" style="margin-top: 18px" :icon="Link" tag="a" :href="image.source_url" target="_blank">
        来源链接
      </el-button>
    </aside>
  </div>
</template>
