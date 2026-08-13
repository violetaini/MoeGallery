<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { mediaUrl } from '../api/client'
import { galleryApi } from '../api/gallery'
import CharacterCard from '../components/CharacterCard.vue'

const characters = ref([])
const works = ref([])
const total = ref(0)
const q = ref('')
const workId = ref()
const page = ref(1)
const pageSize = 48
const workLoading = ref(false)
let workSearchSeq = 0
let listRequestSeq = 0
const publicSettings = ref(null)
const fallbackHeroBackdrop = '/hero/characters-bg.png'
const heroBackdrop = computed(() => {
  const image = publicSettings.value?.characters_hero_image
  return mediaUrl(image, 'preview') || fallbackHeroBackdrop
})

async function load(resetPage = false) {
  const seq = ++listRequestSeq
  if (resetPage) page.value = 1
  const data = await galleryApi.characters({
    q: q.value,
    work_id: workId.value,
    page: page.value,
    page_size: pageSize
  })
  if (seq !== listRequestSeq) return
  characters.value = data.items
  total.value = data.total
}

async function loadWorks(query = '') {
  const seq = ++workSearchSeq
  workLoading.value = true
  try {
    const selected = works.value.find((work) => work.id === workId.value)
    const value = query.trim()
    const data = await galleryApi.works({ page_size: 100, ...(value ? { q: value } : {}) })
    if (seq !== workSearchSeq) return
    works.value = selected && !data.items.some((work) => work.id === selected.id)
      ? [selected, ...data.items]
      : data.items
  } finally {
    if (seq === workSearchSeq) workLoading.value = false
  }
}

function changePage(value) {
  page.value = value
  load()
}

onMounted(async () => {
  await Promise.all([
    galleryApi.publicSettings().then((data) => { publicSettings.value = data }).catch(() => { publicSettings.value = null }),
    loadWorks()
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
    <el-input
      v-model="q"
      clearable
      placeholder="搜索角色"
      :prefix-icon="Search"
      @clear="load(true)"
      @keyup.enter="load(true)"
    />
    <el-select
      v-model="workId"
      clearable
      filterable
      remote
      reserve-keyword
      placeholder="作品"
      :loading="workLoading"
      :remote-method="loadWorks"
      @change="load(true)"
      @visible-change="(visible) => visible && loadWorks()"
    >
      <el-option v-for="work in works" :key="work.id" :label="work.name" :value="work.id" />
    </el-select>
    <el-button @click="load(true)">搜索</el-button>
  </div>
  <div class="grid-cards">
    <CharacterCard v-for="character in characters" :key="character.id" :character="character" />
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
