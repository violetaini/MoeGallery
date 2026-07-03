<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { galleryApi } from '../api/gallery'
import { markImageViewed, shouldTrackImageView } from '../utils/views'
import ImageDetailContent from './ImageDetailContent.vue'

const props = defineProps({
  image: { type: Object, default: null },
  imageId: { type: [Number, String], default: null }
})

const emit = defineEmits(['close'])

const currentImage = ref(null)
const loading = ref(false)
const error = ref('')
let previousHtmlOverflow = ''
let previousBodyOverflow = ''

const normalizedImageId = computed(() => {
  const value = Array.isArray(props.imageId) ? props.imageId[0] : props.imageId
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
})

async function loadImage() {
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

  loading.value = !props.image
  try {
    currentImage.value = await galleryApi.image(normalizedImageId.value)
    await trackViewIfNeeded()
  } catch (caught) {
    if (!props.image) {
      currentImage.value = null
      error.value = caught?.response?.data?.detail || '图片不存在或不可访问'
    }
  } finally {
    loading.value = false
  }
}

async function trackViewIfNeeded() {
  if (!normalizedImageId.value || !shouldTrackImageView(normalizedImageId.value)) {
    return
  }
  try {
    currentImage.value = await galleryApi.trackImageView(normalizedImageId.value)
    markImageViewed(normalizedImageId.value)
  } catch {
    // View tracking is non-critical for opening image details.
  }
}

function close() {
  emit('close')
}

function handleUpdated(updated) {
  currentImage.value = updated
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    close()
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

watch([() => props.image, normalizedImageId], loadImage, { immediate: true })

onMounted(() => {
  lockScroll()
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  restoreScroll()
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div class="image-detail-overlay" @click.self="close">
      <div class="image-detail-overlay__panel" @click.stop>
        <el-button class="image-detail-overlay__close" circle :icon="Close" aria-label="关闭" @click="close" />
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
        <ImageDetailContent v-else :image="currentImage" :loading="loading" @updated="handleUpdated" />
      </div>
    </div>
  </Teleport>
</template>
