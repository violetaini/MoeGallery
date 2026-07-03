<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import { galleryApi } from '../api/gallery'
import ImageMasonry from '../components/ImageMasonry.vue'
import WorkCard from '../components/WorkCard.vue'
import CharacterCard from '../components/CharacterCard.vue'

const route = useRoute()
const router = useRouter()
const q = ref(route.query.q || '')
const result = ref({ images: [], works: [], characters: [], tags: [] })

async function run() {
  if (!q.value.trim()) return
  result.value = await galleryApi.search({ q: q.value.trim() })
  router.replace({ path: '/search', query: { q: q.value.trim() } })
}

watch(() => route.query.q, (value) => {
  q.value = value || ''
  run()
})

onMounted(run)
</script>

<template>
  <section class="listing-hero listing-hero--search">
    <div>
      <span class="hero-eyebrow">Archive search</span>
      <h1>搜索</h1>
      <p>同时检索图片、作品与角色，适合快速定位资料和关联入口。</p>
    </div>
    <div class="listing-hero__meta">{{ result.images.length + result.works.length + result.characters.length }} 个结果</div>
  </section>
  <div class="toolbar search-toolbar">
    <el-input v-model="q" clearable placeholder="关键词" :prefix-icon="SearchIcon" @keyup.enter="run" />
    <el-button @click="run">搜索</el-button>
  </div>
  <div class="section-title"><h2>图片</h2></div>
  <ImageMasonry :images="result.images" />
  <div class="section-title"><h2>作品</h2></div>
  <div class="grid-cards">
    <WorkCard v-for="work in result.works" :key="work.id" :work="work" />
  </div>
  <div class="section-title"><h2>角色</h2></div>
  <div class="grid-cards">
    <CharacterCard v-for="character in result.characters" :key="character.id" :character="character" />
  </div>
</template>
