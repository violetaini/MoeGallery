<script setup>
import { computed } from 'vue'
import { storageUrl } from '../api/client'
import { canUseHdrOriginal } from '../utils/imageDisplay'

const props = defineProps({
  image: { type: Object, default: null },
  alt: { type: String, default: '' },
  imgClass: { type: [String, Array, Object], default: '' },
  pictureClass: { type: [String, Array, Object], default: '' },
  loading: { type: String, default: undefined },
  variant: { type: String, default: 'preview' },
  preferHdr: { type: Boolean, default: false },
  preferAnimated: { type: Boolean, default: false }
})

const originalSrc = computed(() => storageUrl(props.image?.file_path))
const previewSrc = computed(() => storageUrl(props.image?.preview_path || props.image?.file_path || props.image?.thumbnail_path))
const thumbnailSrc = computed(() => storageUrl(props.image?.thumbnail_path || props.image?.preview_path || props.image?.file_path))

const defaultSrc = computed(() => {
  if (props.variant === 'thumbnail') {
    return thumbnailSrc.value
  }
  if (props.variant === 'original') {
    return originalSrc.value || previewSrc.value || thumbnailSrc.value
  }
  return previewSrc.value || thumbnailSrc.value || originalSrc.value
})

const directOriginalSrc = computed(() => {
  if (!props.preferAnimated || !props.image?.is_animated) {
    return ''
  }
  return originalSrc.value
})

const hdrSource = computed(() => {
  if (!props.preferHdr || !canUseHdrOriginal(props.image) || !originalSrc.value) {
    return null
  }
  return {
    src: originalSrc.value,
    type: props.image?.mime_type || undefined,
  }
})

const resolvedSrc = computed(() => directOriginalSrc.value || defaultSrc.value)
</script>

<template>
  <picture v-if="resolvedSrc" :class="['responsive-image', pictureClass]">
    <source
      v-if="hdrSource && !directOriginalSrc"
      media="(dynamic-range: high)"
      :srcset="hdrSource.src"
      :type="hdrSource.type"
    />
    <img :class="imgClass" :src="resolvedSrc" :alt="alt" :loading="loading" />
  </picture>
</template>
