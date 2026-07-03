<script setup>
import { computed } from 'vue'
import { storageUrl } from '../api/client'

const props = defineProps({
  image: { type: Object, required: true },
  styleVars: { type: Object, default: () => ({}) },
  preview: { type: Boolean, default: true }
})

const emit = defineEmits(['open'])

const imageUrl = computed(() => storageUrl(props.image.thumbnail_path || props.image.preview_path || props.image.file_path))
const title = computed(() => props.image.original_filename || props.image.filename || '图片')

function isPlainLeftClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
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
    <a class="image-card" :href="href" :style="styleVars" :aria-label="title" @click="handleClick($event, navigate)">
      <img :src="imageUrl" :alt="title" loading="lazy" />
    </a>
  </RouterLink>
</template>
