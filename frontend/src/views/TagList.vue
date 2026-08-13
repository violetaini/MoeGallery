<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { mediaUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { ratingOptions } from '../constants/ratings'
import ImageMasonry from '../components/ImageMasonry.vue'

const route = useRoute()
const router = useRouter()
const initialRating = String(route.query.rating || 'safe')
const rating = ref(ratingOptions.some((item) => item.value === initialRating) ? initialRating : 'safe')
const images = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 48
const publicSettings = ref(null)
const fallbackHeroBackdrop = '/hero/ratings-bg.png'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.ratings_hero_image
  return mediaUrl(image, 'preview') || fallbackHeroBackdrop
})
let imageRequestSeq = 0
let ratingChangeSeq = 0

const activeRating = computed(() => {
  return ratingOptions.find((item) => item.value === rating.value) || ratingOptions[0]
})

async function loadImages() {
  const seq = ++imageRequestSeq
  const requestedRating = rating.value
  const requestedPage = page.value
  loading.value = true
  try {
    const data = await galleryApi.images({
      rating: requestedRating,
      page: requestedPage,
      page_size: pageSize,
      exclude_cover_images: true,
      exclude_backdrop_images: true,
      exclude_avatar_images: true
    })
    if (seq !== imageRequestSeq) return
    images.value = data.items
    total.value = data.total
  } catch (error) {
    if (seq === imageRequestSeq) ElMessage.error(error?.response?.data?.detail || '加载分级图片失败')
  } finally {
    if (seq === imageRequestSeq) loading.value = false
  }
}

function changePage(value) {
  page.value = value
  loadImages()
}

async function loadPublicSettings() {
  try {
    publicSettings.value = await galleryApi.publicSettings()
  } catch (error) {
    publicSettings.value = null
  }
}

watch(rating, async (value) => {
  const seq = ++ratingChangeSeq
  page.value = 1
  await router.replace({
    path: '/tags',
    query: value === 'safe' ? {} : { rating: value }
  })
  if (seq !== ratingChangeSeq) return
  await loadImages()
}, { immediate: true })

watch(() => route.query.rating, (value) => {
  const normalized = String(value || 'safe')
  const nextRating = ratingOptions.some((item) => item.value === normalized) ? normalized : 'safe'
  if (rating.value !== nextRating) rating.value = nextRating
})

onBeforeUnmount(() => {
  imageRequestSeq += 1
  ratingChangeSeq += 1
})

loadPublicSettings()
</script>

<template>
  <section class="listing-hero listing-hero--rating" :style="{ '--listing-hero-image': `url('${heroBackdrop}')` }">
    <div>
      <span class="hero-eyebrow">Rating library</span>
      <h1>分级</h1>
      <p>{{ activeRating.description }}</p>
    </div>
    <div class="listing-hero__meta">{{ total }} 张图片</div>
  </section>
  <section class="toolbar rating-toolbar">
    <div class="rating-toolbar-copy">
      <h2>{{ activeRating.label }}</h2>
      <span class="muted">切换分级后下方图片墙会即时刷新。</span>
    </div>
    <el-radio-group v-model="rating" class="rating-switch" size="large">
      <el-radio-button v-for="item in ratingOptions" :key="item.value" :label="item.value">
        {{ item.label }}
      </el-radio-button>
    </el-radio-group>
  </section>

  <div class="section-title">
    <h2>{{ activeRating.label }}</h2>
    <span class="muted">{{ total }} 张图片</span>
  </div>
  <ImageMasonry :images="images" :loading="loading" />
  <div v-if="total > pageSize" class="pagination-bar">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      @current-change="changePage"
    />
  </div>
</template>
