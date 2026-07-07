<script setup>
import { computed, ref, watch } from 'vue'
import { storageUrl } from '../api/client'
import { imagePlaceholderFor } from '../utils/imagePlaceholder'

const props = defineProps({
  image: { type: Object, required: true },
  styleVars: { type: Object, default: () => ({}) },
  preview: { type: Boolean, default: true }
})

const emit = defineEmits(['open'])

const imageUrl = computed(() => storageUrl(props.image.thumbnail_path || props.image.preview_path || props.image.file_path))
const placeholderUrl = computed(() => imagePlaceholderFor(props.image))
const title = computed(() => props.image.original_filename || props.image.filename || '图片')
const displayImageUrl = ref('')
const imageRetryCount = ref(0)
const imageLoaded = ref(false)
const maxDisplayRetries = 2
const cardStyle = computed(() => ({
  ...props.styleVars,
  '--image-placeholder': `url("${placeholderUrl.value}")`
}))

watch(
  imageUrl,
  (source) => {
    displayImageUrl.value = source
    imageRetryCount.value = 0
    imageLoaded.value = false
  },
  { immediate: true }
)

function isPlainLeftClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
}

function withRetryParam(source, retry) {
  const separator = source.includes('?') ? '&' : '?'
  return `${source}${separator}agms_img_retry=${retry}&t=${Date.now()}`
}

function handleImageLoad() {
  imageRetryCount.value = 0
  imageLoaded.value = true
}

function handleImageError() {
  imageLoaded.value = false
  if (!imageUrl.value || imageRetryCount.value >= maxDisplayRetries) return
  imageRetryCount.value += 1
  window.setTimeout(() => {
    displayImageUrl.value = withRetryParam(imageUrl.value, imageRetryCount.value)
  }, 260)
}

function handleClick(event, navigate) {
  if (!isPlainLeftClick(event)) {
    return
  }
  if (props.preview) {
    event.preventDefault()
    emit('open', props.image)
    return
  }
  navigate(event)
}
</script>

<template>
  <RouterLink custom :to="`/images/${image.id}`" v-slot="{ href, navigate }">
    <a
      class="image-card"
      :class="{ 'is-image-loaded': imageLoaded }"
      :href="href"
      :style="cardStyle"
      :aria-label="title"
      @click="handleClick($event, navigate)"
    >
      <img :src="displayImageUrl" :alt="title" loading="lazy" @load="handleImageLoad" @error="handleImageError" />
    </a>
  </RouterLink>
</template>
