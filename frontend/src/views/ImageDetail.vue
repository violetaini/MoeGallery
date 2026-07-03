<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { galleryApi } from '../api/gallery'
import ImageDetailContent from '../components/ImageDetailContent.vue'
import { markImageViewed, shouldTrackImageView } from '../utils/views'

const route = useRoute()
const image = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    image.value = await galleryApi.image(route.params.id)
    await trackViewIfNeeded(route.params.id)
  } catch (caught) {
    error.value = caught?.response?.data?.detail || '图片不存在或不可访问'
  } finally {
    loading.value = false
  }
})

function handleUpdated(updated) {
  image.value = updated
}

async function trackViewIfNeeded(imageId) {
  if (!shouldTrackImageView(imageId)) {
    return
  }
  try {
    image.value = await galleryApi.trackImageView(imageId)
    markImageViewed(imageId)
  } catch {
    // View tracking should not block the detail page.
  }
}
</script>

<template>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
  <ImageDetailContent v-else :image="image" :loading="loading" @updated="handleUpdated" />
</template>
