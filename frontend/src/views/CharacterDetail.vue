<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { galleryApi } from '../api/gallery'
import ImageMasonry from '../components/ImageMasonry.vue'
import ResponsiveImage from '../components/ResponsiveImage.vue'

const IMAGE_PAGE_SIZE = 24

const route = useRoute()
const character = ref(null)
const images = ref([])
const imageTotal = ref(0)
const imagePage = ref(1)
const pageLoading = ref(false)
const imageLoading = ref(false)

const characterId = computed(() => route.params.id)

async function loadCharacter() {
  pageLoading.value = true
  try {
    character.value = await galleryApi.character(characterId.value)
    imageTotal.value = character.value.image_count || 0
  } finally {
    pageLoading.value = false
  }
}

async function loadImages() {
  imageLoading.value = true
  try {
    const data = await galleryApi.images({
      character_id: characterId.value,
      page: imagePage.value,
      page_size: IMAGE_PAGE_SIZE
    })
    images.value = data.items
    imageTotal.value = data.total
  } finally {
    imageLoading.value = false
  }
}

async function loadPage() {
  imagePage.value = 1
  images.value = []
  await Promise.all([loadCharacter(), loadImages()])
}

function changeImagePage(nextPage) {
  imagePage.value = nextPage
  loadImages()
}

onMounted(loadPage)
watch(characterId, loadPage)
</script>

<template>
  <div v-loading="pageLoading" class="character-detail-page">
    <template v-if="character">
    <section class="profile-head profile-head--character">
      <ResponsiveImage
        v-if="character.avatar_image"
        :image="character.avatar_image"
        :alt="character.name"
        img-class="cover-image"
        variant="preview"
        prefer-hdr
        prefer-animated
      />
      <div v-else class="cover-image"></div>
      <div class="profile-head__copy">
        <span class="hero-eyebrow">Character profile</span>
        <h1>{{ character.name }}</h1>
        <p class="muted">
          <RouterLink v-if="character.work" :to="`/works/${character.work.id}`">{{ character.work.name }}</RouterLink>
          <span v-if="character.original_name"> · {{ character.original_name }}</span>
        </p>
        <p>{{ character.description || '暂无简介' }}</p>
        <div class="chip-row">
          <el-tag v-if="character.work" effect="dark">{{ character.work.name }}</el-tag>
          <el-tag type="success">{{ imageTotal }} 张关联图片</el-tag>
        </div>
      </div>
    </section>
    <div class="section-title">
      <h2>相关图片</h2>
      <span class="muted">每页 {{ IMAGE_PAGE_SIZE }} 张，共 {{ imageTotal }} 张</span>
    </div>
    <div v-loading="imageLoading" class="character-detail-images">
      <ImageMasonry v-if="images.length" :images="images" />
      <el-empty v-else-if="!imageLoading" description="暂无关联图片" />
    </div>
    <div v-if="imageTotal > IMAGE_PAGE_SIZE" class="pagination-bar">
      <el-pagination
        background
        layout="prev, pager, next"
        :current-page="imagePage"
        :page-size="IMAGE_PAGE_SIZE"
        :total="imageTotal"
        @current-change="changeImagePage"
      />
    </div>
    </template>
  </div>
</template>
