<script setup>
import { ref, watch } from 'vue'
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
let searchRequestSeq = 0

function clearResults() {
  result.value = { images: [], works: [], characters: [], tags: [] }
}

async function loadFromRoute(value) {
  const seq = ++searchRequestSeq
  const normalized = String(value || '').trim()
  q.value = normalized
  if (!normalized) {
    if (seq === searchRequestSeq) clearResults()
    return
  }
  const data = await galleryApi.search({ q: normalized })
  if (seq === searchRequestSeq) result.value = data
}

async function submit() {
  const normalized = q.value.trim()
  const current = String(route.query.q || '').trim()
  if (normalized === current) {
    await loadFromRoute(normalized)
    return
  }
  await router.replace({ path: '/search', query: normalized ? { q: normalized } : {} })
}

watch(() => route.query.q, loadFromRoute, { immediate: true })
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
    <el-input v-model="q" clearable placeholder="关键词" :prefix-icon="SearchIcon" @clear="submit" @keyup.enter="submit" />
    <el-button @click="submit">搜索</el-button>
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
