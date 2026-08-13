<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { mediaUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import WorkCard from '../components/WorkCard.vue'

const works = ref([])
const total = ref(0)
const q = ref('')
const page = ref(1)
const pageSize = 48
const publicSettings = ref(null)
let listRequestSeq = 0
const fallbackHeroBackdrop = '/hero/works-bg.jpg'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.works_hero_image
  return mediaUrl(image, 'preview') || fallbackHeroBackdrop
})

async function load(resetPage = false) {
  const seq = ++listRequestSeq
  if (resetPage) page.value = 1
  const data = await galleryApi.works({
    q: q.value,
    page: page.value,
    page_size: pageSize
  })
  if (seq !== listRequestSeq) return
  works.value = data.items
  total.value = data.total
}

function changePage(value) {
  page.value = value
  load()
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
    <el-input
      v-model="q"
      clearable
      placeholder="搜索作品"
      :prefix-icon="Search"
      @clear="load(true)"
      @keyup.enter="load(true)"
    />
    <el-button @click="load(true)">搜索</el-button>
  </div>
  <div class="grid-cards">
    <WorkCard v-for="work in works" :key="work.id" :work="work" />
  </div>
  <div v-if="total > pageSize" class="pagination-bar">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      @current-change="changePage"
    />
  </div>
</template>
