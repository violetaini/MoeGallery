<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ArrowLeft, ArrowRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { imageLoadingPlaceholders } from '../utils/imagePlaceholder'

const fallbackImage = imageLoadingPlaceholders.landscape
const slides = ref([])
const loading = ref(false)
const activeIndex = ref(0)
const paused = ref(false)
const progressKey = ref(0)
const railRef = ref(null)
const activeDisplayImageSrc = ref(fallbackImage)
const activeImageLoaded = ref(false)
const activeImageRetryCount = ref(0)
const exiting = ref(false)
const slideInterval = 5600
const maxActiveImageRetries = 2
let slideTimer = null
const railDrag = {
  active: false,
  moved: false,
  startX: 0,
  scrollLeft: 0
}

const activeSlide = computed(() => slides.value[activeIndex.value] || null)
const activeImageSrc = computed(() => imageSrc(activeSlide.value))
const activeTitle = computed(() => activeSlide.value?.original_filename || activeSlide.value?.filename || 'Anime Gallery')
const slideshowStyle = computed(() => ({
  '--home-slideshow-image': `url("${activeImageLoaded.value ? activeDisplayImageSrc.value : fallbackImage}")`,
  '--home-progress-duration': `${slideInterval}ms`
}))

function imageSrc(image) {
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackImage
}

function thumbnailSrc(image) {
  return storageUrl(image?.thumbnail_path || image?.preview_path || image?.file_path) || fallbackImage
}

function withRetryParam(source, retry) {
  const separator = source.includes('?') ? '&' : '?'
  return `${source}${separator}agms_home_retry=${retry}&t=${Date.now()}`
}

function handleActiveImageLoad() {
  activeImageRetryCount.value = 0
  activeImageLoaded.value = true
}

function handleActiveImageError() {
  activeImageLoaded.value = false
  if (!activeImageSrc.value || activeImageRetryCount.value >= maxActiveImageRetries) {
    activeDisplayImageSrc.value = fallbackImage
    activeImageLoaded.value = true
    return
  }
  activeImageRetryCount.value += 1
  window.setTimeout(() => {
    activeDisplayImageSrc.value = withRetryParam(activeImageSrc.value, activeImageRetryCount.value)
  }, 260)
}

function preloadHomeImage(source) {
  if (exiting.value || typeof window === 'undefined' || !source || source === fallbackImage) return
  const image = new window.Image()
  image.decoding = 'async'
  image.src = source
}

function preloadNearbySlides() {
  if (exiting.value || !slides.value.length) return
  const indexes = [activeIndex.value, activeIndex.value + 1, activeIndex.value - 1, activeIndex.value + 2]
  const sources = indexes
    .map((index) => slides.value[(index + slides.value.length) % slides.value.length])
    .map((slide) => imageSrc(slide))
    .filter(Boolean)
  Array.from(new Set(sources)).forEach(preloadHomeImage)
}

function clearSlideTimer() {
  if (slideTimer) {
    window.clearTimeout(slideTimer)
    slideTimer = null
  }
}

function scheduleSlideTimer() {
  clearSlideTimer()
  progressKey.value += 1
  if (paused.value || slides.value.length <= 1) return
  slideTimer = window.setTimeout(() => {
    goNext()
  }, slideInterval)
}

function chooseSlide(index) {
  if (!slides.value.length) return
  activeIndex.value = (index + slides.value.length) % slides.value.length
  scheduleSlideTimer()
}

function goPrevious() {
  chooseSlide(activeIndex.value - 1)
}

function goNext() {
  chooseSlide(activeIndex.value + 1)
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
  chooseSlide(index)
}

async function loadSlides() {
  loading.value = true
  try {
    const settings = await galleryApi.publicSettings().catch(() => null)
    const configuredSlides = settings?.home_slideshow_images || []
    if (configuredSlides.length) {
      slides.value = configuredSlides
      activeIndex.value = 0
      return
    }
    let data = await galleryApi.images({
      page: 1,
      page_size: 12,
      orientation: 'landscape',
      sort: 'random'
    })
    if (!data.items?.length) {
      data = await galleryApi.images({
        page: 1,
        page_size: 12,
        sort: 'random'
      })
    }
    slides.value = data.items || []
    activeIndex.value = 0
  } catch (error) {
    slides.value = []
  } finally {
    loading.value = false
    scheduleSlideTimer()
  }
}

onMounted(loadSlides)
onBeforeUnmount(clearSlideTimer)

onBeforeRouteLeave(() => {
  exiting.value = true
  paused.value = true
  clearSlideTimer()
})

watch(
  activeImageSrc,
  (source) => {
    activeDisplayImageSrc.value = source || fallbackImage
    activeImageRetryCount.value = 0
    activeImageLoaded.value = false
    preloadNearbySlides()
  },
  { immediate: true }
)

watch(
  () => [slides.value.length, activeIndex.value],
  () => preloadNearbySlides()
)
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
        <div class="home-slide-frame" :class="{ 'home-slide-frame--empty': !activeSlide, 'is-image-loaded': activeImageLoaded }">
          <img
            :key="`${activeSlide?.id || 'fallback'}-${activeDisplayImageSrc}`"
            :src="activeDisplayImageSrc"
            :alt="activeTitle"
            loading="eager"
            decoding="async"
            fetchpriority="high"
            @load="handleActiveImageLoad"
            @error="handleActiveImageError"
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
        <div
          v-if="slides.length > 1 && !paused"
          :key="progressKey"
          class="home-slideshow__progress"
        ></div>
      </div>
    </div>

    <div v-if="slides.length" class="home-slideshow__rail-wrap" aria-label="胶片切换">
      <button
        v-if="slides.length > 4"
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
        aria-label="放映缩略图"
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
          type="button"
          :aria-label="slide.original_filename || slide.filename || `图片 ${slide.id}`"
          @pointerdown.stop
          @dragstart.prevent
          @click.stop="handleThumbClick(index)"
        >
          <img
            :src="thumbnailSrc(slide)"
            :alt="slide.original_filename || slide.filename || '图片'"
            loading="lazy"
            decoding="async"
            draggable="false"
          />
        </button>
      </div>
      <button
        v-if="slides.length > 4"
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
