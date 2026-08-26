<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Close } from '@element-plus/icons-vue'
import { mediaUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import { markImageViewed, shouldTrackImageView } from '../utils/views'
import ImageDetailContent from './ImageDetailContent.vue'

const props = defineProps({
  image: { type: Object, default: null },
  imageId: { type: [Number, String], default: null },
  images: { type: Array, default: () => [] },
  shareToken: { type: String, default: '' }
})

const emit = defineEmits(['close', 'navigate'])

const currentImage = ref(null)
const loading = ref(false)
const error = ref('')
const overlayRef = ref(null)
let previousHtmlOverflow = ''
let previousBodyOverflow = ''
let imageLoadSequence = 0
let prefetchSequence = 0
let navigationDirection = 0
const preloadedSources = new Map()
const maxPreloadedSources = 12
const swipeState = {
  pointerId: null,
  startX: 0,
  startY: 0
}

const normalizedImageId = computed(() => {
  const value = Array.isArray(props.imageId) ? props.imageId[0] : props.imageId
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
})

const imageIndex = computed(() => props.images.findIndex((image) => image?.id === normalizedImageId.value))
const previousImage = computed(() => (imageIndex.value > 0 ? props.images[imageIndex.value - 1] : null))
const nextImage = computed(() => (
  imageIndex.value >= 0 && imageIndex.value < props.images.length - 1
    ? props.images[imageIndex.value + 1]
    : null
))
const imagePositionLabel = computed(() => (
  imageIndex.value >= 0 && props.images.length > 1 ? `${imageIndex.value + 1} / ${props.images.length}` : ''
))

async function loadImage() {
  const requestSequence = ++imageLoadSequence
  error.value = ''
  if (props.image) {
    currentImage.value = props.image
  }

  if (!normalizedImageId.value) {
    if (!props.image) {
      currentImage.value = null
    }
    loading.value = false
    return
  }

  loading.value = !props.image || Boolean(props.shareToken)
  try {
    const loadedImage = props.shareToken
      ? await galleryApi.shareImage(props.shareToken, normalizedImageId.value)
      : await galleryApi.image(normalizedImageId.value)
    if (requestSequence !== imageLoadSequence) return
    currentImage.value = loadedImage
    if (!props.shareToken) {
      await trackViewIfNeeded(requestSequence)
    }
  } catch (caught) {
    if (requestSequence !== imageLoadSequence) return
    if (!props.image || props.shareToken) {
      currentImage.value = null
      error.value = caught?.response?.data?.detail || '图片不存在或不可访问'
    }
  } finally {
    loading.value = false
  }
}

async function trackViewIfNeeded(requestSequence) {
  if (!normalizedImageId.value || !shouldTrackImageView(normalizedImageId.value)) {
    return
  }
  try {
    const updatedImage = await galleryApi.trackImageView(normalizedImageId.value)
    if (requestSequence !== imageLoadSequence) return
    currentImage.value = updatedImage
    markImageViewed(normalizedImageId.value)
  } catch {
    // View tracking is non-critical for opening image details.
  }
}

function viewerPreloadSource(image) {
  if (!image) return ''
  return mediaUrl(image, image.is_animated ? 'original' : 'preview', props.shareToken)
}

function preloadViewerSource(source) {
  if (!source || typeof window === 'undefined') return Promise.resolve(false)
  if (preloadedSources.has(source)) return preloadedSources.get(source).promise

  const image = new window.Image()
  image.decoding = 'async'
  image.fetchPriority = 'low'
  let resolveLoad
  const promise = new Promise((resolve) => {
    resolveLoad = resolve
  })
  preloadedSources.set(source, { image, promise })
  while (preloadedSources.size > maxPreloadedSources) {
    const oldestSource = preloadedSources.keys().next().value
    preloadedSources.delete(oldestSource)
  }
  image.onload = () => resolveLoad(true)
  image.onerror = () => {
    preloadedSources.delete(source)
    resolveLoad(false)
  }
  image.src = source
  return promise
}

function preloadNeighbors(direction = 0) {
  if (imageIndex.value < 0 || !props.images.length) return
  const offsets = direction > 0
    ? [1, 2, 3]
    : direction < 0
      ? [-1, -2, -3]
      : [1, 2, 3, -1, -2]
  const sources = offsets
    .map((offset) => props.images[imageIndex.value + offset])
    .map(viewerPreloadSource)
    .filter(Boolean)
  if (!sources.length) return

  const sequence = ++prefetchSequence
  let cursor = 0
  const workerCount = Math.min(2, sources.length)
  const workers = Array.from({ length: workerCount }, async () => {
    while (sequence === prefetchSequence && cursor < sources.length) {
      const source = sources[cursor]
      cursor += 1
      await preloadViewerSource(source)
    }
  })
  void Promise.allSettled(workers)
}

function navigate(direction) {
  const targetImage = direction < 0 ? previousImage.value : nextImage.value
  if (!targetImage) return
  navigationDirection = direction
  emit('navigate', targetImage)
}

function startSwipe(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  swipeState.pointerId = event.pointerId
  swipeState.startX = event.clientX
  swipeState.startY = event.clientY
}

function finishSwipe(event) {
  if (swipeState.pointerId !== event.pointerId) return
  const distanceX = event.clientX - swipeState.startX
  const distanceY = event.clientY - swipeState.startY
  swipeState.pointerId = null
  if (Math.abs(distanceX) < 56 || Math.abs(distanceX) <= Math.abs(distanceY) * 1.25) return
  navigate(distanceX < 0 ? 1 : -1)
}

function cancelSwipe() {
  swipeState.pointerId = null
}

function close() {
  emit('close')
}

function handleOverlayClick(event) {
  if (event.target !== event.currentTarget || typeof window === 'undefined') return
  const edgeWidth = Math.min(168, Math.max(24, window.innerWidth * 0.08))
  if (event.clientX <= edgeWidth || event.clientX >= window.innerWidth - edgeWidth) {
    close()
  }
}

function handleUpdated(updated) {
  currentImage.value = updated
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    close()
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    navigate(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    navigate(1)
  }
}

function lockScroll() {
  previousHtmlOverflow = document.documentElement.style.overflow
  previousBodyOverflow = document.body.style.overflow
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
}

function restoreScroll() {
  document.documentElement.style.overflow = previousHtmlOverflow
  document.body.style.overflow = previousBodyOverflow
}

watch([() => props.image, normalizedImageId, () => props.shareToken], () => {
  void loadImage()
  preloadNeighbors(navigationDirection)
  navigationDirection = 0
}, { immediate: true })

watch(() => props.images, () => preloadNeighbors(0), { deep: true })

onMounted(() => {
  lockScroll()
  window.requestAnimationFrame(() => overlayRef.value?.focus())
})

onBeforeUnmount(() => {
  imageLoadSequence += 1
  prefetchSequence += 1
  preloadedSources.clear()
  restoreScroll()
})
</script>

<template>
  <Teleport to="body">
    <div ref="overlayRef" class="image-detail-overlay" tabindex="-1" @click="handleOverlayClick" @keydown="handleKeydown">
      <el-button
        v-if="previousImage"
        class="image-detail-overlay__nav image-detail-overlay__nav--previous"
        circle
        :icon="ArrowLeft"
        title="上一张"
        aria-label="上一张"
        @click="navigate(-1)"
      />
      <div
        class="image-detail-overlay__panel"
        @click.stop
        @pointerdown="startSwipe"
        @pointerup="finishSwipe"
        @pointercancel="cancelSwipe"
      >
        <el-button class="image-detail-overlay__close" circle :icon="Close" aria-label="关闭" @click="close" />
        <span v-if="imagePositionLabel" class="image-detail-overlay__position">{{ imagePositionLabel }}</span>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
        <ImageDetailContent v-else :image="currentImage" :loading="loading" :share-token="shareToken" @updated="handleUpdated" />
      </div>
      <el-button
        v-if="nextImage"
        class="image-detail-overlay__nav image-detail-overlay__nav--next"
        circle
        :icon="ArrowRight"
        title="下一张"
        aria-label="下一张"
        @click="navigate(1)"
      />
    </div>
  </Teleport>
</template>
