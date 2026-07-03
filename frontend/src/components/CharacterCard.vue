<script setup>
import ResponsiveImage from './ResponsiveImage.vue'

const props = defineProps({
  character: { type: Object, required: true }
})
</script>

<template>
  <RouterLink class="entity-card entity-card--character" :to="`/characters/${character.id}`">
    <div class="entity-card__media">
      <ResponsiveImage
        v-if="character.avatar_image"
        :image="character.avatar_image"
        :alt="character.name"
        img-class="entity-thumb entity-thumb--character"
        variant="thumbnail"
        loading="lazy"
      />
      <div v-else class="entity-thumb entity-thumb--character"></div>
      <div class="entity-card__overlay">
        <span class="entity-card__eyebrow">角色档案</span>
      </div>
    </div>
    <div class="entity-card-body">
      <h3>{{ character.name }}</h3>
      <div class="muted">{{ character.work?.name || '未绑定作品' }}</div>
    </div>
  </RouterLink>
</template>
