<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storageUrl } from '../api/client'

const props = defineProps({
  images: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectedIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['edit', 'toggle-selection'])

const wallRef = ref(null)
const containerWidth = ref(0)

const gap = 4
const targetRowHeight = computed(() => {
  if (containerWidth.value <= 480) return 132
  if (containerWidth.value <= 760) return 150
  return 180
})

function updateWidth() {
  containerWidth.value = wallRef.value?.clientWidth || 0
}

function isSelected(imageId) {
  return props.selectedIds.includes(imageId)
}

function toggleSelection(image, checked) {
  emit('toggle-selection', image, checked)
}

function openEditor(image) {
  emit('edit', image)
}

let resizeObserver

onMounted(() => {
  updateWidth()
  resizeObserver = new ResizeObserver(updateWidth)
  if (wallRef.value) resizeObserver.observe(wallRef.value)
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

function imageTitle(row) {
  return row.original_filename || row.filename || '图片'
}
</script>

<template>
  <div ref="wallRef" class="admin-image-wall">
    <template v-if="rows.length">
      <div
        v-for="(row, rowIndex) in rows"
        :key="rowIndex"
        class="admin-image-wall-row"
        :class="{ 'admin-image-wall-row--loose': !row.justified }"
        :style="{ '--row-height': `${row.height}px`, '--gallery-gap': `${gap}px` }"
      >
        <div
          v-for="{ image, width } in row.items"
          :key="image.id"
          class="admin-image-wall-item"
          :class="{ 'is-selected': isSelected(image.id) }"
          :style="{ flex: `0 0 ${width}px`, width: `${width}px` }"
        >
          <button class="admin-image-wall-media" type="button" :aria-label="imageTitle(image)" @click="openEditor(image)">
            <img :src="storageUrl(image.thumbnail_path || image.preview_path || image.file_path)" :alt="imageTitle(image)" loading="lazy" />
          </button>
          <el-checkbox
            class="admin-image-wall-check"
            :model-value="isSelected(image.id)"
            @change="(checked) => toggleSelection(image, checked)"
            @click.stop
          />
        </div>
      </div>
    </template>
    <div v-else-if="!loading" class="empty-state">还没有图片，去后台上传第一批作品吧。</div>
  </div>
</template>
