<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { galleryApi } from '../api/gallery'
import ImageMasonry from '../components/ImageMasonry.vue'

const route = useRoute()
const share = ref(null)
const loading = ref(false)
const failed = ref(false)
let requestSeq = 0

const token = computed(() => String(route.params.token || ''))
const imageCountLabel = computed(() => `${share.value?.image_count || 0} 张图片`)

async function load() {
  const seq = ++requestSeq
  loading.value = true
  failed.value = false
  try {
    const data = await galleryApi.share(token.value)
    if (seq === requestSeq) share.value = data
  } catch {
    if (seq === requestSeq) {
      share.value = null
      failed.value = true
    }
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

onMounted(load)
watch(token, load)
</script>

<template>
  <section class="share-page">
    <el-skeleton v-if="loading" :rows="10" animated />
    <el-result v-else-if="failed" icon="warning" title="分享不存在或已撤销" sub-title="请向分享者索取新的链接。" />
    <template v-else-if="share">
      <header class="share-page__header">
        <div>
          <p class="eyebrow">Shared gallery</p>
          <h1>{{ share.title }}</h1>
        </div>
        <el-tag type="info" effect="plain">{{ imageCountLabel }}</el-tag>
      </header>
      <ImageMasonry :images="share.images" :share-token="share.token" />
    </template>
  </section>
</template>
