<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { orientationOptions } from '../constants/orientations'
import { ratingOptions } from '../constants/ratings'
import ImageMasonry from '../components/ImageMasonry.vue'

const route = useRoute()
const images = ref([])
const works = ref([])
const characters = ref([])
const publicSettings = ref(null)
const total = ref(0)
const loading = ref(false)
const preloading = ref(false)
const loadMoreSentinel = ref(null)
const page = ref(1)
const pageSize = 48
const preloadedPage = ref(null)
const preloadedItems = ref([])
const preloadedTotal = ref(0)
const filters = reactive({
  work_id: undefined,
  character_id: undefined,
  rating: undefined,
  orientation: undefined,
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
let loadObserver = null
let loadSeq = 0
let preloadSeq = 0
let preloadTargetPage = null
let preloadPromise = null
let loadingMore = false
const assetPreloadConcurrency = 6
const assetPreloadRetries = 1
const assetPreloadTimeout = 12000

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
  if (filters.orientation) return `${orientationOptions.find((item) => item.value === filters.orientation)?.label || filters.orientation}画廊`
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

function activeImageParams(targetPage) {
  return {
    page: targetPage,
    page_size: pageSize,
    require_work_related: true,
    require_character_related: true,
    ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== undefined))
  }
}

function preloadSingleAsset(source) {
  if (typeof window === 'undefined') return Promise.resolve(false)

  return new Promise((resolve) => {
    let attempt = 0

    const start = () => {
      let settled = false
      const preload = new window.Image()
      const timer = window.setTimeout(() => finish(false), assetPreloadTimeout)

      const finish = (ok) => {
        if (settled) return
        settled = true
        window.clearTimeout(timer)
        preload.onload = null
        preload.onerror = null
        if (!ok && attempt < assetPreloadRetries) {
          attempt += 1
          window.setTimeout(start, 220)
          return
        }
        resolve(ok)
      }

      preload.decoding = 'async'
      preload.loading = 'eager'
      preload.onload = () => finish(true)
      preload.onerror = () => finish(false)
      preload.src = source
    }

    start()
  })
}

async function preloadImageAssets(items = [], seq = preloadSeq) {
  if (typeof window === 'undefined') return
  const sources = [
    ...new Set(
      items
        .map((image) => storageUrl(image.thumbnail_path || image.preview_path || image.file_path))
        .filter(Boolean)
    )
  ]
  if (!sources.length) return

  let cursor = 0
  const workerCount = Math.min(assetPreloadConcurrency, sources.length)
  const workers = Array.from({ length: workerCount }, async () => {
    while (cursor < sources.length && seq === preloadSeq) {
      const source = sources[cursor]
      cursor += 1
      await preloadSingleAsset(source)
    }
  })
  await Promise.allSettled(workers)
}

function clearPreload() {
  preloadSeq += 1
  preloadTargetPage = null
  preloadPromise = null
  preloading.value = false
  preloadedPage.value = null
  preloadedItems.value = []
  preloadedTotal.value = 0
}

function observeLoadMoreSentinel() {
  loadObserver?.disconnect()
  if (!loadMoreSentinel.value || !hasMore.value) return
  loadObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        loadMore()
      }
    },
    {
      root: null,
      rootMargin: '720px 0px',
      threshold: 0.01
    }
  )
  loadObserver.observe(loadMoreSentinel.value)
}

async function preloadNextPage() {
  if (preloading.value || loading.value || !hasMore.value) return
  const nextPage = page.value + 1
  if (preloadedPage.value === nextPage) return

  const seq = ++preloadSeq
  preloadTargetPage = nextPage
  preloading.value = true
  preloadPromise = galleryApi.images(activeImageParams(nextPage))

  try {
    const data = await preloadPromise
    if (seq !== preloadSeq) return
    preloadedPage.value = nextPage
    preloadedItems.value = data.items || []
    preloadedTotal.value = data.total || 0
    void preloadImageAssets(preloadedItems.value, seq)
  } catch (error) {
    if (seq === preloadSeq) {
      preloadedPage.value = null
      preloadedItems.value = []
      preloadedTotal.value = 0
    }
  } finally {
    if (seq === preloadSeq) {
      preloadTargetPage = null
      preloadPromise = null
      preloading.value = false
    }
  }
}

async function loadImages(reset = false) {
  if (loading.value) return
  const seq = ++loadSeq
  let shouldPreload = false
  loading.value = true
  if (reset) {
    page.value = 1
    images.value = []
    total.value = 0
    clearPreload()
  }
  try {
    const data = await galleryApi.images(activeImageParams(page.value))
    if (seq !== loadSeq) return
    images.value = reset ? data.items : [...images.value, ...data.items]
    total.value = data.total
    await nextTick()
    observeLoadMoreSentinel()
    shouldPreload = true
  } finally {
    if (seq === loadSeq) {
      loading.value = false
    }
  }
  if (shouldPreload && seq === loadSeq) {
    preloadNextPage()
  }
}

async function loadMore() {
  if (loading.value || loadingMore || !hasMore.value) return
  const nextPage = page.value + 1
  const expectedLoadSeq = loadSeq
  const expectedPreloadSeq = preloadSeq

  loadingMore = true
  try {
    if (preloading.value && preloadTargetPage === nextPage && preloadPromise) {
      await preloadPromise.catch(() => null)
      if (expectedLoadSeq !== loadSeq || expectedPreloadSeq !== preloadSeq) return
    }

    if (preloadedPage.value === nextPage) {
      page.value = nextPage
      images.value = [...images.value, ...preloadedItems.value]
      total.value = preloadedTotal.value || total.value
      clearPreload()
      await nextTick()
      observeLoadMoreSentinel()
      preloadNextPage()
      return
    }

    page.value += 1
    await loadImages()
  } finally {
    loadingMore = false
  }
}

function resetFilters() {
  filters.work_id = undefined
  filters.character_id = undefined
  filters.rating = undefined
  filters.orientation = undefined
  filters.sort = 'latest'
  loadImages(true)
}

onMounted(async () => {
  filters.work_id = route.query.work_id ? Number(route.query.work_id) : undefined
  filters.character_id = route.query.character_id ? Number(route.query.character_id) : undefined
  filters.rating = route.query.rating || undefined
  filters.orientation = route.query.orientation || undefined
  await Promise.all([loadPublicSettings(), loadFilters()])
  await loadImages(true)
})

onBeforeUnmount(() => {
  clearPreload()
  loadObserver?.disconnect()
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
    <el-select
      v-model="filters.orientation"
      clearable
      placeholder="方向"
      @change="loadImages(true)"
    >
      <el-option v-for="orientation in orientationOptions" :key="orientation.value" :label="orientation.label" :value="orientation.value" />
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
  <div v-if="hasMore" ref="loadMoreSentinel" class="gallery-load-sentinel" @click="loadMore">
    <span v-if="loading">正在加载更多...</span>
    <span v-else-if="preloading">下一页已在预加载，继续下滑</span>
    <span v-else>继续下滑自动加载更多</span>
  </div>
</template>
