<script setup>
import ResponsiveImage from './ResponsiveImage.vue'

const props = defineProps({
  work: { type: Object, required: true }
})
</script>

<template>
  <RouterLink class="entity-card entity-card--work" :to="`/works/${work.id}`">
    <div class="entity-card__media">
      <ResponsiveImage
        v-if="work.cover_image"
        :image="work.cover_image"
        :alt="work.name"
        img-class="entity-thumb"
        variant="thumbnail"
        loading="lazy"
      />
      <div v-else class="entity-thumb"></div>
      <div class="entity-card__overlay">
        <span class="entity-card__eyebrow">作品档案</span>
      </div>
    </div>
    <div class="entity-card-body">
      <h3>{{ work.name }}</h3>
      <div class="muted">{{ work.original_name || '未填写原名' }}</div>
    </div>
  </RouterLink>
</template>
