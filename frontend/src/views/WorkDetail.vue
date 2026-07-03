<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Calendar, Collection, Link, Picture, Star, Timer, User } from '@element-plus/icons-vue'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import CharacterCard from '../components/CharacterCard.vue'
import ImageMasonry from '../components/ImageMasonry.vue'
import ResponsiveImage from '../components/ResponsiveImage.vue'
import { canUseHdrOriginal } from '../utils/imageDisplay'

const CHARACTER_CARD_MIN_WIDTH = 180
const CHARACTER_GRID_GAP = 16
const CHARACTER_MAX_PAGE_SIZE = 24
const IMAGE_PAGE_SIZE = 24

const route = useRoute()
const work = ref(null)
const characters = ref([])
const characterTotal = ref(0)
const characterPage = ref(1)
const characterSectionRef = ref(null)
const characterColumnCount = ref(1)
const images = ref([])
const imageTotal = ref(0)
const imagePage = ref(1)
const pageLoading = ref(false)
const characterLoading = ref(false)
const imageLoading = ref(false)
const prefersHdr = ref(false)

const workId = computed(() => route.params.id)
const backdrop = computed(() => {
  const image = work.value?.backdrop_image || work.value?.cover_image
  if (!image) return ''
  const highDynamicRangePath = prefersHdr.value && canUseHdrOriginal(image) ? image.file_path : ''
  return storageUrl(highDynamicRangePath || image.preview_path || image.thumbnail_path || image.file_path)
})
const heroStyle = computed(() => (backdrop.value ? { '--work-backdrop-image': `url("${backdrop.value}")` } : {}))
const createdAt = computed(() => {
  if (!work.value?.created_at) return ''
  return new Date(work.value.created_at).toLocaleDateString()
})
const genreList = computed(() => splitList(work.value?.genres))
const studioList = computed(() => splitList(work.value?.studios))
const runtimeText = computed(() => {
  if (!work.value?.run_time_minutes) return ''
  return `${work.value.run_time_minutes} 分钟`
})
const ratingText = computed(() => {
  if (!work.value?.community_rating) return ''
  return Number(work.value.community_rating).toFixed(1)
})
const characterPageSize = computed(() => {
  return Math.min(CHARACTER_MAX_PAGE_SIZE, Math.max(1, characterColumnCount.value))
})

let characterResizeObserver
let characterResizeFallbackActive = false
let hdrMediaQuery

function splitList(value) {
  return String(value || '')
    .split(/[、,，/]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function loadWork() {
  pageLoading.value = true
  try {
    work.value = await galleryApi.work(workId.value)
  } finally {
    pageLoading.value = false
  }
}

async function loadCharacters() {
  characterLoading.value = true
  try {
    const data = await galleryApi.characters({
      work_id: workId.value,
      page: characterPage.value,
      page_size: characterPageSize.value
    })
    characters.value = data.items
    characterTotal.value = data.total
  } finally {
    characterLoading.value = false
  }
}

async function loadImages() {
  imageLoading.value = true
  try {
    const data = await galleryApi.images({
      work_id: workId.value,
      page: imagePage.value,
      page_size: IMAGE_PAGE_SIZE
    })
    images.value = data.items
    imageTotal.value = data.total
  } finally {
    imageLoading.value = false
  }
}

function changeCharacterPage(nextPage) {
  characterPage.value = nextPage
  loadCharacters()
}

function changeImagePage(nextPage) {
  imagePage.value = nextPage
  loadImages()
}

function updateCharacterColumns() {
  const section = characterSectionRef.value
  if (!section) return
  const styles = window.getComputedStyle(section)
  const horizontalPadding = Number.parseFloat(styles.paddingLeft) + Number.parseFloat(styles.paddingRight)
  const contentWidth = Math.max(0, section.clientWidth - horizontalPadding)
  const nextColumns = Math.max(
    1,
    Math.floor((contentWidth + CHARACTER_GRID_GAP) / (CHARACTER_CARD_MIN_WIDTH + CHARACTER_GRID_GAP))
  )
  characterColumnCount.value = nextColumns
}

function startCharacterObserver(section) {
  stopCharacterObserver()
  updateCharacterColumns()
  if (window.ResizeObserver) {
    characterResizeObserver = new ResizeObserver(updateCharacterColumns)
    characterResizeObserver.observe(section)
  } else {
    window.addEventListener('resize', updateCharacterColumns)
    characterResizeFallbackActive = true
  }
}

function stopCharacterObserver() {
  if (characterResizeObserver) {
    characterResizeObserver.disconnect()
    characterResizeObserver = null
  }
  if (characterResizeFallbackActive) {
    window.removeEventListener('resize', updateCharacterColumns)
    characterResizeFallbackActive = false
  }
}

function updateDynamicRangePreference() {
  prefersHdr.value = Boolean(hdrMediaQuery?.matches)
}

watch(characterSectionRef, async (section) => {
  await nextTick()
  if (!section) {
    stopCharacterObserver()
    return
  }
  startCharacterObserver(section)
}, { flush: 'post' })

onMounted(() => {
  if (characterSectionRef.value) {
    startCharacterObserver(characterSectionRef.value)
  }
  if (window.matchMedia) {
    hdrMediaQuery = window.matchMedia('(dynamic-range: high)')
    updateDynamicRangePreference()
    if (hdrMediaQuery.addEventListener) {
      hdrMediaQuery.addEventListener('change', updateDynamicRangePreference)
    } else {
      hdrMediaQuery.addListener?.(updateDynamicRangePreference)
    }
  }
})

onBeforeUnmount(() => {
  stopCharacterObserver()
  if (hdrMediaQuery?.removeEventListener) {
    hdrMediaQuery.removeEventListener('change', updateDynamicRangePreference)
  } else {
    hdrMediaQuery?.removeListener?.(updateDynamicRangePreference)
  }
})

watch(workId, async () => {
  work.value = null
  characters.value = []
  images.value = []
  characterPage.value = 1
  imagePage.value = 1
  await Promise.all([loadWork(), loadCharacters(), loadImages()])
}, {
  immediate: true
})

watch(characterPageSize, async (nextSize, previousSize) => {
  if (nextSize === previousSize || !work.value) return
  const lastPage = Math.max(1, Math.ceil(characterTotal.value / nextSize))
  if (characterPage.value > lastPage) {
    characterPage.value = lastPage
  }
  await loadCharacters()
})
</script>

<template>
  <el-skeleton v-if="pageLoading && !work" :rows="10" animated />
  <div v-else-if="work" class="work-detail">
    <section class="work-hero jellyfin-work-hero" :style="heroStyle">
      <div class="work-poster-frame">
        <ResponsiveImage
          v-if="work.cover_image"
          :image="work.cover_image"
          :alt="work.name"
          img-class="work-poster"
          variant="preview"
          prefer-hdr
          prefer-animated
        />
        <div v-else class="work-poster work-poster--empty"></div>
      </div>
      <div class="work-hero-copy">
        <div class="work-kicker">
          <el-icon><Collection /></el-icon>
          <span>作品</span>
        </div>
        <h1>{{ work.name }}</h1>
        <p v-if="work.original_name" class="work-original">{{ work.original_name }}</p>
        <p v-if="work.tagline" class="work-tagline">{{ work.tagline }}</p>
        <div class="work-meta">
          <el-tag v-if="work.production_year" effect="dark">
            <el-icon><Calendar /></el-icon>
            {{ work.production_year }}
          </el-tag>
          <el-tag v-if="runtimeText" effect="dark">
            <el-icon><Timer /></el-icon>
            {{ runtimeText }}
          </el-tag>
          <el-tag v-if="ratingText" effect="dark">
            <el-icon><Star /></el-icon>
            {{ ratingText }}
          </el-tag>
          <el-tag v-if="work.content_rating" effect="dark">
            {{ work.content_rating }}
          </el-tag>
          <el-tag effect="dark">
            <el-icon><User /></el-icon>
            {{ characterTotal }} 位角色
          </el-tag>
          <el-tag effect="dark">
            <el-icon><Picture /></el-icon>
            {{ imageTotal }} 张图片
          </el-tag>
        </div>
        <div class="work-actions">
          <el-button v-if="work.official_site" tag="a" :href="work.official_site" target="_blank" rel="noreferrer" type="primary" :icon="Link">
            外部资料
          </el-button>
          <el-button text bg>
            {{ work.status || '资料库条目' }}
          </el-button>
        </div>
        <div class="work-facts">
          <div v-if="genreList.length">
            <span>类型</span>
            <strong>{{ genreList.join(' / ') }}</strong>
          </div>
          <div v-if="studioList.length">
            <span>制作</span>
            <strong>{{ studioList.join(' / ') }}</strong>
          </div>
          <div v-if="createdAt">
            <span>入库</span>
            <strong>{{ createdAt }}</strong>
          </div>
        </div>
        <div class="work-overview">
          <h2>概览</h2>
          <p>{{ work.description || '暂无简介' }}</p>
        </div>
      </div>
    </section>

    <section ref="characterSectionRef" class="media-section">
      <div class="section-title media-section-title">
        <div>
          <h2>角色</h2>
          <span class="muted">每页 {{ characterPageSize }} 位，共 {{ characterTotal }} 位</span>
        </div>
        <el-pagination
          v-if="characterTotal > characterPageSize"
          v-model:current-page="characterPage"
          small
          background
          layout="prev, pager, next"
          :page-size="characterPageSize"
          :total="characterTotal"
          @current-change="changeCharacterPage"
        />
      </div>
      <el-skeleton v-if="characterLoading" :rows="4" animated />
      <div v-else-if="characters.length" class="grid-cards work-character-grid">
        <CharacterCard v-for="character in characters" :key="character.id" :character="character" />
      </div>
      <div v-else class="empty-state">这个作品还没有绑定角色。</div>
    </section>

    <section class="media-section">
      <div class="section-title media-section-title">
        <div>
          <h2>图片</h2>
          <span class="muted">每页 {{ IMAGE_PAGE_SIZE }} 张，共 {{ imageTotal }} 张</span>
        </div>
        <el-pagination
          v-if="imageTotal > IMAGE_PAGE_SIZE"
          v-model:current-page="imagePage"
          small
          background
          layout="prev, pager, next"
          :page-size="IMAGE_PAGE_SIZE"
          :total="imageTotal"
          @current-change="changeImagePage"
        />
      </div>
      <ImageMasonry :images="images" :loading="imageLoading" />
      <div v-if="imageTotal > IMAGE_PAGE_SIZE" class="pagination-bar">
        <el-pagination
          v-model:current-page="imagePage"
          background
          layout="prev, pager, next, total"
          :page-size="IMAGE_PAGE_SIZE"
          :total="imageTotal"
          @current-change="changeImagePage"
        />
      </div>
    </section>
  </div>
</template>
