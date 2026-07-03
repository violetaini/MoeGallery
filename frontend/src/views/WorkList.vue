<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import WorkCard from '../components/WorkCard.vue'

const works = ref([])
const total = ref(0)
const q = ref('')
const publicSettings = ref(null)
const fallbackHeroBackdrop = '/hero/works-bg.jpg'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.works_hero_image
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackHeroBackdrop
})

async function load() {
  const data = await galleryApi.works({ q: q.value, page_size: 100 })
  works.value = data.items
  total.value = data.total
}

async function loadPublicSettings() {
  try {
    publicSettings.value = await galleryApi.publicSettings()
  } catch (error) {
    publicSettings.value = null
  }
}

onMounted(async () => {
  await Promise.all([loadPublicSettings(), load()])
})
</script>

<template>
  <section class="listing-hero listing-hero--work" :style="{ '--listing-hero-image': `url('${heroBackdrop}')` }">
    <div>
      <span class="hero-eyebrow">Series archive</span>
      <h1>作品索引</h1>
      <p>按条目整理的作品入口，适合快速定位封面、角色与图库归属。</p>
    </div>
    <div class="listing-hero__meta">{{ total }} 个作品</div>
  </section>
  <div class="toolbar search-toolbar">
    <el-input v-model="q" clearable placeholder="搜索作品" :prefix-icon="Search" @keyup.enter="load" />
    <el-button @click="load">搜索</el-button>
  </div>
  <div class="grid-cards">
    <WorkCard v-for="work in works" :key="work.id" :work="work" />
  </div>
</template>
