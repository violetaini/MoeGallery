<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, ArrowRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'

const fallbackImage = '/hero/gallery-bg.jpg'
const slides = ref([])
const loading = ref(false)
const activeIndex = ref(0)
const paused = ref(false)
const progressKey = ref(0)
const railRef = ref(null)
const slideInterval = 5600
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
  '--home-slideshow-image': `url("${activeImageSrc.value}")`,
  '--home-progress-duration': `${slideInterval}ms`
}))

function imageSrc(image) {
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackImage
}

function thumbnailSrc(image) {
  return storageUrl(image?.thumbnail_path || image?.preview_path || image?.file_path) || fallbackImage
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
    const data = await galleryApi.images({
      page: 1,
      page_size: 12,
      sort: 'random'
    })
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
</script>

<template>
  <section
    class="home-slideshow"
    :class="{ 'is-paused': paused, 'is-loading': loading, 'is-empty': !slides.length }"
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
        <div class="home-slide-frame" :class="{ 'home-slide-frame--empty': !activeSlide }">
          <img :key="activeSlide?.id || 'fallback'" :src="activeImageSrc" :alt="activeTitle" />
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
          <img :src="thumbnailSrc(slide)" :alt="slide.original_filename || slide.filename || '图片'" draggable="false" />
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
