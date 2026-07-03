<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ImageCard from './ImageCard.vue'
import ImageDetailOverlay from './ImageDetailOverlay.vue'

const props = defineProps({
  images: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  preview: { type: Boolean, default: true }
})

const route = useRoute()
const router = useRouter()
const galleryRef = ref(null)
const containerWidth = ref(0)

const gap = 4
const targetRowHeight = computed(() => {
  if (containerWidth.value <= 480) return 132
  if (containerWidth.value <= 760) return 150
  return 180
})

const activeImageId = computed(() => {
  const value = Array.isArray(route.query.image) ? route.query.image[0] : route.query.image
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
})

const activeImage = computed(() => {
  if (!activeImageId.value) return null
  return props.images.find((image) => image.id === activeImageId.value) || null
})

function updateWidth() {
  containerWidth.value = galleryRef.value?.clientWidth || 0
}

function openImageOverlay(image) {
  if (!props.preview) return
  router.replace({
    query: {
      ...route.query,
      image: image.id
    }
  })
}

function closeImageOverlay() {
  const query = { ...route.query }
  delete query.image
  router.replace({ query })
}

let resizeObserver

onMounted(() => {
  updateWidth()
  resizeObserver = new ResizeObserver(updateWidth)
  if (galleryRef.value) resizeObserver.observe(galleryRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

watch(() => props.images.length, () => nextTick(updateWidth))

const rows = computed(() => {
  if (!containerWidth.value || !props.images.length) return []

  const availableWidth = containerWidth.value
  const rowHeight = targetRowHeight.value
  const result = []
  let row = []
  let ratioSum = 0

  props.images.forEach((image) => {
    const ratio = image.width && image.height ? image.width / image.height : 1
    row.push({ image, ratio })
    ratioSum += ratio

    const rowWidth = ratioSum * rowHeight + gap * Math.max(0, row.length - 1)
    if (rowWidth >= availableWidth) {
      const availableImageWidth = Math.max(1, availableWidth - gap * (row.length - 1))
      const height = Math.min(Math.min(260, rowHeight * 1.45), availableImageWidth / ratioSum)
      result.push({
        items: row.map((item) => ({ ...item, width: item.ratio * height })),
        height,
        justified: true
      })
      row = []
      ratioSum = 0
    }
  })

  if (row.length) {
    const availableImageWidth = Math.max(1, availableWidth - gap * (row.length - 1))
    const height = Math.min(rowHeight, availableImageWidth / ratioSum)
    result.push({
      items: row.map((item) => ({ ...item, width: item.ratio * height })),
      height,
      justified: false
    })
  }

  return result
})
</script>

<template>
  <div ref="galleryRef" class="masonry">
    <template v-if="rows.length">
      <div
        v-for="(row, rowIndex) in rows"
        :key="rowIndex"
        class="masonry-row"
        :class="{ 'masonry-row--loose': !row.justified }"
        :style="{ '--row-height': `${row.height}px`, '--gallery-gap': `${gap}px` }"
      >
        <ImageCard
          v-for="{ image, width } in row.items"
          :key="image.id"
          :image="image"
          :style-vars="{ flex: `0 0 ${width}px`, width: `${width}px` }"
          :preview="preview"
          @open="openImageOverlay"
        />
      </div>
    </template>
    <div v-else-if="!loading" class="empty-state">还没有图片，去后台上传第一批作品吧。</div>
    <ImageDetailOverlay
      v-if="preview && activeImageId"
      :image-id="activeImageId"
      :image="activeImage"
      @close="closeImageOverlay"
    />
  </div>
</template>
