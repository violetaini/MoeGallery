<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storageUrl } from '../api/client'
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
const publicSettings = ref(null)
const fallbackHeroBackdrop = '/hero/ratings-bg.png'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.ratings_hero_image
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackHeroBackdrop
})

const activeRating = computed(() => {
  return ratingOptions.find((item) => item.value === rating.value) || ratingOptions[0]
})

async function loadImages() {
  loading.value = true
  try {
    const data = await galleryApi.images({
      rating: rating.value,
      page: 1,
      page_size: 100
    })
    images.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadPublicSettings() {
  try {
    publicSettings.value = await galleryApi.publicSettings()
  } catch (error) {
    publicSettings.value = null
  }
}

watch(rating, async (value) => {
  await router.replace({
    path: '/tags',
    query: value === 'safe' ? {} : { rating: value }
  })
  await loadImages()
}, { immediate: true })

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
</template>
