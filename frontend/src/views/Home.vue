<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ArrowLeft, ArrowRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { mediaUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { imageLoadingPlaceholders } from '../utils/imagePlaceholder'

const fallbackImage = imageLoadingPlaceholders.landscape
const slides = ref([])
const loading = ref(false)
const activeIndex = ref(0)
const paused = ref(false)
const railRef = ref(null)
const activeDisplayImageSrc = ref(fallbackImage)
const pendingDisplayImageSrc = ref('')
const pendingImageLoaded = ref(false)
const pendingSlideIndex = ref(-1)
const activeImageRetryCount = ref(0)
const exiting = ref(false)
const slideInterval = 5600
const maxActiveImageRetries = 2
const initialSlideLoadConcurrency = 3
const randomSlideCount = 24
const preloadedImages = new Map()
let slideTimer = null
let imageSwapTimer = null
let preloadGeneration = 0
let slideRequestSequence = 0
let backgroundPreloadFrame = null
let backgroundPreloadIdleCallback = null
let backgroundPreloadTimer = null
const railDrag = {
  active: false,
  moved: false,
  startX: 0,
  scrollLeft: 0
}

const activeSlide = computed(() => slides.value[activeIndex.value] || null)
const activeImageSrc = computed(() => homeSlideImageSrc(activeSlide.value))
const activeTitle = computed(() => activeSlide.value?.original_filename || activeSlide.value?.filename || 'Anime Gallery')
const slideshowStyle = computed(() => ({
  '--home-slideshow-image': `url("${activeDisplayImageSrc.value || fallbackImage}")`
}))

// The filmstrip and player deliberately share this exact media source.
function homeSlideImageSrc(image) {
  return mediaUrl(image, 'preview') || mediaUrl(image, 'original') || fallbackImage
}

function withRetryParam(source, retry) {
  const separator = source.includes('?') ? '&' : '?'
  return `${source}${separator}agms_home_retry=${retry}&t=${Date.now()}`
}

function handleActiveImageLoad() {
  activeImageRetryCount.value = 0
}

function handleActiveImageError() {
  if (!activeImageSrc.value || activeImageRetryCount.value >= maxActiveImageRetries) {
    return
  }
  activeImageRetryCount.value += 1
  window.setTimeout(() => {
    activeDisplayImageSrc.value = withRetryParam(activeImageSrc.value, activeImageRetryCount.value)
  }, 260)
}

function preloadHomeImage(source, priority = 'low') {
  if (exiting.value || typeof window === 'undefined' || !source || source === fallbackImage) return null
  if (preloadedImages.has(source)) {
    const cached = preloadedImages.get(source)
    if (priority === 'high') cached.image.fetchPriority = 'high'
    return cached.promise
  }

  const image = new window.Image()
  image.decoding = 'async'
  image.fetchPriority = priority
  let resolveLoad
  const promise = new Promise((resolve) => {
    resolveLoad = resolve
  })
  preloadedImages.set(source, { image, promise })
  image.onload = async () => {
    try {
      await image.decode()
    } catch {
      // A completed load remains usable if decode() is unavailable or races disposal.
    }
    resolveLoad(true)
  }
  image.onerror = () => {
    preloadedImages.delete(source)
    resolveLoad(false)
  }
  image.src = source
  return promise
}

function preloadSlide(index, priority = 'low') {
  if (exiting.value || !slides.value.length) return null
  const normalizedIndex = (index + slides.value.length) % slides.value.length
  return preloadHomeImage(homeSlideImageSrc(slides.value[normalizedIndex]), priority)
}

function clearSlideTimer() {
  if (slideTimer) {
    window.clearTimeout(slideTimer)
    slideTimer = null
  }
}

function clearImageSwapTimer() {
  if (imageSwapTimer) {
    window.clearTimeout(imageSwapTimer)
    imageSwapTimer = null
  }
}

function clearBackgroundPreloadSchedule() {
  if (typeof window === 'undefined') return
  if (backgroundPreloadFrame !== null) {
    window.cancelAnimationFrame(backgroundPreloadFrame)
    backgroundPreloadFrame = null
  }
  if (backgroundPreloadIdleCallback !== null && typeof window.cancelIdleCallback === 'function') {
    window.cancelIdleCallback(backgroundPreloadIdleCallback)
    backgroundPreloadIdleCallback = null
  }
  if (backgroundPreloadTimer !== null) {
    window.clearTimeout(backgroundPreloadTimer)
    backgroundPreloadTimer = null
  }
}

function clearPendingImage() {
  pendingDisplayImageSrc.value = ''
  pendingImageLoaded.value = false
  pendingSlideIndex.value = -1
}

function handlePendingImageLoad() {
  if (!pendingDisplayImageSrc.value || pendingSlideIndex.value < 0) return

  const requestSequence = slideRequestSequence
  const nextSource = pendingDisplayImageSrc.value
  const nextIndex = pendingSlideIndex.value
  pendingImageLoaded.value = true
  clearImageSwapTimer()
  imageSwapTimer = window.setTimeout(() => {
    if (
      requestSequence !== slideRequestSequence
      || exiting.value
      || pendingDisplayImageSrc.value !== nextSource
    ) return

    activeIndex.value = nextIndex
    activeDisplayImageSrc.value = nextSource
    activeImageRetryCount.value = 0

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (
          requestSequence !== slideRequestSequence
          || exiting.value
          || pendingDisplayImageSrc.value !== nextSource
        ) return
        clearPendingImage()
        scheduleSlideTimer()
      })
    })
  }, 190)
}

function handlePendingImageError() {
  clearImageSwapTimer()
  clearPendingImage()
  scheduleSlideTimer()
}

function scheduleSlideTimer() {
  clearSlideTimer()
  if (paused.value || slides.value.length <= 1) return
  slideTimer = window.setTimeout(() => {
    goNext()
  }, slideInterval)
}

async function chooseSlide(index) {
  if (!slides.value.length || exiting.value) return
  const targetIndex = (index + slides.value.length) % slides.value.length
  const requestSequence = ++slideRequestSequence

  clearSlideTimer()
  clearImageSwapTimer()
  clearPendingImage()
  if (targetIndex === activeIndex.value) {
    scheduleSlideTimer()
    return
  }

  const targetSource = homeSlideImageSrc(slides.value[targetIndex])
  const loaded = targetSource === fallbackImage || await preloadHomeImage(targetSource, 'high')
  if (requestSequence !== slideRequestSequence || exiting.value) return

  if (loaded) {
    pendingImageLoaded.value = false
    pendingSlideIndex.value = targetIndex
    pendingDisplayImageSrc.value = targetSource
    return
  }
  scheduleSlideTimer()
}

function goPrevious() {
  void chooseSlide(activeIndex.value - 1)
}

function goNext() {
  void chooseSlide(activeIndex.value + 1)
}

function togglePaused() {
  paused.value = !paused.value
  scheduleSlideTimer()
}

function scrollRail(direction) {
  const rail = railRef.value
  if (!rail) return
  const distance = Math.max(240, rail.clientWidth * 0.7)
  rail.scrollBy({ left: direction * distance, behavior: 'smooth' })
}

function handleRailWheel(event) {
  const rail = railRef.value
  if (!rail) return
  if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return
  event.preventDefault()
  rail.scrollBy({ left: event.deltaY, behavior: 'auto' })
}

function startRailDrag(event) {
  const rail = railRef.value
  if (!rail || (event.button !== undefined && event.button !== 0)) return
  railDrag.active = true
  railDrag.moved = false
  railDrag.startX = event.clientX
  railDrag.scrollLeft = rail.scrollLeft
  rail.classList.add('is-dragging')
  rail.setPointerCapture?.(event.pointerId)
}

function moveRailDrag(event) {
  const rail = railRef.value
  if (!railDrag.active || !rail) return
  const distance = event.clientX - railDrag.startX
  if (Math.abs(distance) > 4) railDrag.moved = true
  rail.scrollLeft = railDrag.scrollLeft - distance
}

function endRailDrag(event) {
  const rail = railRef.value
  if (!railDrag.active || !rail) return
  railDrag.active = false
  rail.classList.remove('is-dragging')
  rail.releasePointerCapture?.(event.pointerId)
}

function handleThumbClick(index) {
  if (railDrag.moved) {
    railDrag.moved = false
    return
  }
  void chooseSlide(index)
}

function appendLoadedSlide(candidate, source, generation) {
  if (generation !== preloadGeneration || exiting.value || slides.value.some((slide) => slide.id === candidate.id)) {
    return false
  }

  const isFirstReady = slides.value.length === 0
  slides.value.push(candidate)
  if (isFirstReady) {
    activeIndex.value = 0
    activeImageRetryCount.value = 0
    if (source !== activeDisplayImageSrc.value) {
      pendingImageLoaded.value = false
      pendingSlideIndex.value = 0
      pendingDisplayImageSrc.value = source
    }
  }
  if (slides.value.length === 2) scheduleSlideTimer()
  return true
}

async function loadHomeSlideCandidate(candidate, generation, priority) {
  const source = homeSlideImageSrc(candidate)
  const loaded = source === fallbackImage || await preloadHomeImage(source, priority)
  if (!loaded) return false
  return appendLoadedSlide(candidate, source, generation)
}

function visibleRailSlotCount(candidateCount) {
  if (!candidateCount) return 0
  const railWidth = railRef.value?.clientWidth || window.innerWidth || 0
  const cardSpan = window.innerWidth <= 520 ? 84 : window.innerWidth <= 760 ? 110 : 166
  return Math.min(candidateCount, Math.max(4, Math.ceil(railWidth / cardSpan) + 1))
}

async function loadInitialRailSlides(candidates, generation) {
  await nextTick()
  const visibleSlots = visibleRailSlotCount(candidates.length)
  let cursor = 0

  async function worker() {
    while (generation === preloadGeneration && !exiting.value && cursor < candidates.length && slides.value.length < visibleSlots) {
      const candidate = candidates[cursor]
      cursor += 1
      await loadHomeSlideCandidate(candidate, generation, 'high')
    }
  }

  const workerCount = Math.min(initialSlideLoadConcurrency, candidates.length)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  const loadedIds = new Set(slides.value.map((slide) => slide.id))
  return candidates.filter((candidate) => !loadedIds.has(candidate.id))
}

function scheduleBackgroundSlidePreload(candidates, generation) {
  if (!candidates.length || typeof window === 'undefined') return

  const startPreload = () => {
    backgroundPreloadIdleCallback = null
    backgroundPreloadTimer = null
    if (generation !== preloadGeneration || exiting.value) return

    // Start every remaining home image together only after the first viewport is stable.
    candidates.forEach((candidate) => {
      void loadHomeSlideCandidate(candidate, generation, 'low')
    })
  }

  const waitForIdle = () => {
    backgroundPreloadFrame = null
    if (typeof window.requestIdleCallback === 'function') {
      backgroundPreloadIdleCallback = window.requestIdleCallback(startPreload, { timeout: 1200 })
    } else {
      backgroundPreloadTimer = window.setTimeout(startPreload, 180)
    }
  }

  backgroundPreloadFrame = window.requestAnimationFrame(waitForIdle)
}

async function setSlides(items) {
  const candidates = Array.isArray(items) ? items.filter(Boolean) : []
  const generation = ++preloadGeneration
  clearBackgroundPreloadSchedule()
  clearImageSwapTimer()
  clearPendingImage()
  clearSlideTimer()
  slides.value = []
  activeIndex.value = 0
  activeDisplayImageSrc.value = fallbackImage
  activeImageRetryCount.value = 0
  slideRequestSequence += 1

  if (!candidates.length) return { generation, remainingCandidates: [] }

  const remainingCandidates = await loadInitialRailSlides(candidates, generation)
  return { generation, remainingCandidates }
}

async function loadSlides() {
  let preloadPlan = null
  loading.value = true
  try {
    // Most galleries use the random feed. Start it with the settings request to
    // remove one network round trip before the first image can begin loading.
    const settingsRequest = galleryApi.publicSettings().catch(() => null)
    const randomSlidesRequest = galleryApi.images({
      page: 1,
      page_size: randomSlideCount,
      orientation: 'landscape',
      sort: 'random',
      exclude_cover_images: true,
      exclude_backdrop_images: true,
      exclude_avatar_images: true
    }).catch(() => null)
    const settings = await settingsRequest
    const configuredSlides = settings?.home_slideshow_images || []
    if (configuredSlides.length) {
      preloadPlan = await setSlides(configuredSlides)
      return
    }
    let data = await randomSlidesRequest
    if (!data?.items?.length) {
      data = await galleryApi.images({
        page: 1,
        page_size: randomSlideCount,
        sort: 'random',
        exclude_cover_images: true,
        exclude_backdrop_images: true,
        exclude_avatar_images: true
      })
    }
    preloadPlan = await setSlides(data.items || [])
  } catch (error) {
    preloadPlan = await setSlides([])
  } finally {
    loading.value = false
    scheduleSlideTimer()
    if (preloadPlan && preloadPlan.generation === preloadGeneration && !exiting.value) {
      scheduleBackgroundSlidePreload(preloadPlan.remainingCandidates, preloadPlan.generation)
    }
  }
}

onMounted(loadSlides)
onBeforeUnmount(() => {
  preloadGeneration += 1
  slideRequestSequence += 1
  clearSlideTimer()
  clearImageSwapTimer()
  clearBackgroundPreloadSchedule()
  preloadedImages.clear()
})

onBeforeRouteLeave(() => {
  exiting.value = true
  paused.value = true
  preloadGeneration += 1
  slideRequestSequence += 1
  clearSlideTimer()
  clearImageSwapTimer()
  clearBackgroundPreloadSchedule()
})
</script>

<template>
  <section
    class="home-slideshow"
    :class="{ 'is-paused': paused, 'is-loading': loading, 'is-empty': !slides.length, 'is-exiting': exiting }"
    :style="slideshowStyle"
  >
    <div class="home-slideshow__backdrop"></div>
    <div class="home-slideshow__scan"></div>

    <div class="home-slideshow__layout">
      <div class="home-slideshow__copy">
        <h1 class="home-slideshow__title">
          <span>Anime</span>
          <span>Gallery</span>
        </h1>
      </div>

      <div class="home-slideshow__visual">
        <div class="home-slide-shadow" aria-hidden="true"></div>
        <div class="home-slide-frame">
          <img
            class="home-slide-frame__current"
            :src="activeDisplayImageSrc"
            :alt="activeTitle"
            loading="eager"
            decoding="async"
            fetchpriority="high"
            @load="handleActiveImageLoad"
            @error="handleActiveImageError"
          />
          <img
            v-if="pendingDisplayImageSrc"
            class="home-slide-frame__pending"
            :class="{ 'is-image-loaded': pendingImageLoaded }"
            :src="pendingDisplayImageSrc"
            alt=""
            aria-hidden="true"
            loading="eager"
            decoding="async"
            fetchpriority="high"
            @load="handlePendingImageLoad"
            @error="handlePendingImageError"
          />
        </div>

        <div class="home-slideshow__controls" v-show="slides.length > 1">
          <el-button circle :icon="ArrowLeft" title="上一张" aria-label="上一张" @click="goPrevious" />
          <el-button
            circle
            :icon="paused ? VideoPlay : VideoPause"
            :title="paused ? '继续放映' : '暂停放映'"
            :aria-label="paused ? '继续放映' : '暂停放映'"
            @click="togglePaused"
          />
          <el-button circle :icon="ArrowRight" title="下一张" aria-label="下一张" @click="goNext" />
        </div>
      </div>
    </div>

    <div
      class="home-slideshow__rail-wrap has-rail-controls"
      :class="{ 'is-empty': !slides.length }"
      aria-label="胶片切换"
      :aria-busy="loading"
    >
      <button
        class="home-rail-button home-rail-button--prev"
        type="button"
        title="向左滑动"
        aria-label="向左滑动"
        @click="scrollRail(-1)"
      >
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <div
        ref="railRef"
        class="home-slideshow__rail"
        aria-label="放映图片"
        @wheel="handleRailWheel"
        @pointerdown="startRailDrag"
        @pointermove="moveRailDrag"
        @pointerup="endRailDrag"
        @pointercancel="endRailDrag"
        @pointerleave="endRailDrag"
      >
        <button
          v-for="(slide, index) in slides"
          :key="slide.id"
          class="home-slide-thumb"
          :class="{ 'is-active': index === activeIndex }"
          :style="{ '--home-film-delay': `${Math.min(index, 6) * 45}ms` }"
          type="button"
          :aria-label="slide.original_filename || slide.filename || `图片 ${slide.id}`"
          @pointerenter="preloadSlide(index)"
          @focus="preloadSlide(index)"
          @pointerdown.stop="preloadSlide(index)"
          @dragstart.prevent
          @click.stop="handleThumbClick(index)"
        >
          <img
            :src="homeSlideImageSrc(slide)"
            :alt="slide.original_filename || slide.filename || '图片'"
            loading="lazy"
            decoding="async"
            draggable="false"
          />
        </button>
      </div>
      <button
        class="home-rail-button home-rail-button--next"
        type="button"
        title="向右滑动"
        aria-label="向右滑动"
        @click="scrollRail(1)"
      >
        <el-icon><ArrowRight /></el-icon>
      </button>
    </div>
  </section>
</template>
