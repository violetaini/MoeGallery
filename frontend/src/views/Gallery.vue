<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { ratingOptions } from '../constants/ratings'
import ImageMasonry from '../components/ImageMasonry.vue'

const route = useRoute()
const images = ref([])
const works = ref([])
const characters = ref([])
const publicSettings = ref(null)
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 48
const filters = reactive({
  work_id: undefined,
  character_id: undefined,
  rating: undefined,
  sort: 'latest'
})
const optionLoading = reactive({
  works: false,
  characters: false
})
const optionSearchSeq = {
  works: 0,
  characters: 0
}

const hasMore = computed(() => images.value.length < total.value)
const fallbackHeroBackdrop = '/hero/gallery-bg.jpg'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.home_hero_image
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackHeroBackdrop
})
const activeFilterLabel = computed(() => {
  if (filters.character_id) return '角色视角'
  if (filters.work_id) return '作品视角'
  if (filters.rating) return `${ratingOptions.find((item) => item.value === filters.rating)?.label || filters.rating}分级`
  return '精选画廊'
})

function optionParams(query) {
  const q = query?.trim()
  return q ? { page_size: 100, q } : { page_size: 100 }
}

async function loadWorks(query = '') {
  const seq = ++optionSearchSeq.works
  optionLoading.works = true
  try {
    const data = await galleryApi.works(optionParams(query))
    if (seq === optionSearchSeq.works) {
      works.value = data.items
    }
  } finally {
    if (seq === optionSearchSeq.works) {
      optionLoading.works = false
    }
  }
}

async function loadCharacters(query = '') {
  const seq = ++optionSearchSeq.characters
  optionLoading.characters = true
  try {
    const data = await galleryApi.characters(optionParams(query))
    if (seq === optionSearchSeq.characters) {
      characters.value = data.items
    }
  } finally {
    if (seq === optionSearchSeq.characters) {
      optionLoading.characters = false
    }
  }
}

async function loadFilters() {
  await Promise.all([loadWorks(), loadCharacters()])
}

async function loadPublicSettings() {
  try {
    publicSettings.value = await galleryApi.publicSettings()
  } catch (error) {
    publicSettings.value = null
  }
}

async function loadImages(reset = false) {
  if (loading.value) return
  loading.value = true
  if (reset) {
    page.value = 1
    images.value = []
  }
  const data = await galleryApi.images({
    page: page.value,
    page_size: pageSize,
    require_work_related: true,
    require_character_related: true,
    ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== undefined))
  })
  images.value = reset ? data.items : [...images.value, ...data.items]
  total.value = data.total
  loading.value = false
}

function loadMore() {
  page.value += 1
  loadImages()
}

function resetFilters() {
  filters.work_id = undefined
  filters.character_id = undefined
  filters.rating = undefined
  filters.sort = 'latest'
  loadImages(true)
}

onMounted(async () => {
  filters.work_id = route.query.work_id ? Number(route.query.work_id) : undefined
  filters.character_id = route.query.character_id ? Number(route.query.character_id) : undefined
  filters.rating = route.query.rating || undefined
  await Promise.all([loadPublicSettings(), loadFilters()])
  await loadImages(true)
})
</script>

<template>
  <section class="hero-panel hero-panel--anime" :style="{ '--hero-anime-image': `url('${heroBackdrop}')` }">
    <div class="hero-panel__copy">
      <div class="hero-panel__lead">
        <div class="hero-eyebrow">{{ activeFilterLabel }}</div>
        <h1>Anime Gallery</h1>
        <p>围绕作品、角色与分级组织的图像档案，在同一页里完成浏览、筛选与对照。</p>
        <div class="hero-links">
          <RouterLink class="hero-link-chip" to="/works">作品</RouterLink>
          <RouterLink class="hero-link-chip" to="/characters">角色</RouterLink>
          <RouterLink class="hero-link-chip" to="/tags">分级</RouterLink>
        </div>
      </div>
    </div>
  </section>

  <section class="toolbar gallery-toolbar">
    <el-select
      v-model="filters.work_id"
      clearable
      filterable
      remote
      reserve-keyword
      placeholder="搜索作品"
      :loading="optionLoading.works"
      :remote-method="loadWorks"
      @change="loadImages(true)"
      @visible-change="(visible) => visible && loadWorks()"
    >
      <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
    </el-select>
    <el-select
      v-model="filters.character_id"
      clearable
      filterable
      remote
      reserve-keyword
      placeholder="搜索角色"
      :loading="optionLoading.characters"
      :remote-method="loadCharacters"
      @change="loadImages(true)"
      @visible-change="(visible) => visible && loadCharacters()"
    >
      <el-option v-for="character in characters" :key="character.id" :label="character.name" :value="character.id" />
    </el-select>
    <el-select
      v-model="filters.rating"
      clearable
      placeholder="分级"
      @change="loadImages(true)"
    >
      <el-option v-for="rating in ratingOptions" :key="rating.value" :label="rating.label" :value="rating.value" />
    </el-select>
    <el-select v-model="filters.sort" @change="loadImages(true)">
      <el-option label="最新上传" value="latest" />
      <el-option label="随机漫游" value="random" />
      <el-option label="收藏最多" value="favorites" />
      <el-option label="分辨率最高" value="resolution" />
    </el-select>
    <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
  </section>

  <div class="section-title">
    <h2>图片墙</h2>
    <span class="muted">{{ total }} 张图片</span>
  </div>
  <ImageMasonry :images="images" :loading="loading" />
  <div v-if="hasMore" style="display: flex; justify-content: center; margin-top: 22px">
    <el-button size="large" :loading="loading" @click="loadMore">加载更多</el-button>
  </div>
</template>
