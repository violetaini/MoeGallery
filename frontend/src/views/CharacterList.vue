<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { storageUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import CharacterCard from '../components/CharacterCard.vue'

const characters = ref([])
const works = ref([])
const total = ref(0)
const q = ref('')
const workId = ref()
const publicSettings = ref(null)
const fallbackHeroBackdrop = '/hero/characters-bg.png'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.characters_hero_image
  return storageUrl(image?.preview_path || image?.file_path || image?.thumbnail_path) || fallbackHeroBackdrop
})

async function load() {
  const data = await galleryApi.characters({ q: q.value, work_id: workId.value, page_size: 100 })
  characters.value = data.items
  total.value = data.total
}

onMounted(async () => {
  await Promise.all([
    galleryApi.publicSettings().then((data) => { publicSettings.value = data }).catch(() => { publicSettings.value = null }),
    galleryApi.works({ page_size: 100 }).then((data) => { works.value = data.items })
  ])
  await load()
})
</script>

<template>
  <section class="listing-hero listing-hero--character" :style="{ '--listing-hero-image': `url('${heroBackdrop}')` }">
    <div>
      <span class="hero-eyebrow">Character archive</span>
      <h1>角色索引</h1>
      <p>围绕角色头像、归属作品与关联图片做快速检索，适合连续浏览与对照。</p>
    </div>
    <div class="listing-hero__meta">{{ total }} 位角色</div>
  </section>
  <div class="toolbar character-toolbar">
    <el-input v-model="q" clearable placeholder="搜索角色" :prefix-icon="Search" @keyup.enter="load" />
    <el-select v-model="workId" clearable filterable placeholder="作品" @change="load">
      <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
    </el-select>
    <el-button @click="load">搜索</el-button>
  </div>
  <div class="grid-cards">
    <CharacterCard v-for="character in characters" :key="character.id" :character="character" />
  </div>
</template>
