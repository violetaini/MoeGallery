<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { galleryApi } from '../api/gallery'
import ImageMasonry from '../components/ImageMasonry.vue'
import ResponsiveImage from '../components/ResponsiveImage.vue'

const route = useRoute()
const character = ref(null)
const images = ref([])

onMounted(async () => {
  character.value = await galleryApi.character(route.params.id)
  const data = await galleryApi.images({ character_id: route.params.id, page_size: 48 })
  images.value = data.items
})
</script>

<template>
  <div v-if="character">
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
          <el-tag v-if="images.length" type="success">{{ images.length }} 张关联图片</el-tag>
        </div>
      </div>
    </section>
    <div class="section-title">
      <h2>相关图片</h2>
    </div>
    <ImageMasonry :images="images" />
  </div>
</template>
