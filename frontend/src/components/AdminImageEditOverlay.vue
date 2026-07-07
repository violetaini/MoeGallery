<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { galleryApi } from '../api/gallery'
import { orientationLabel } from '../constants/orientations'
import { ratingLabel, ratingOptions, ratingTagType } from '../constants/ratings'
import ResponsiveImage from './ResponsiveImage.vue'

const props = defineProps({
  image: { type: Object, required: true }
})

const emit = defineEmits(['close', 'saved'])

const saving = ref(false)
const form = reactive({
  original_filename: '',
  artist_name: '',
  source_url: '',
  rating: 'safe',
  is_public: true,
  favorite_count: 0
})

let previousHtmlOverflow = ''
let previousBodyOverflow = ''

const title = computed(() => props.image?.original_filename || props.image?.filename || '图片')
const dimensions = computed(() => (
  props.image?.width && props.image?.height ? `${props.image.width} x ${props.image.height}` : '-'
))
const fileSize = computed(() => (
  typeof props.image?.file_size === 'number' ? `${Math.round(props.image.file_size / 1024)} KB` : '-'
))
const mimeType = computed(() => props.image?.mime_type || '-')
const dynamicRangeLabel = computed(() => (props.image?.dynamic_range === 'hdr' ? 'HDR' : 'SDR'))
const bitDepthLabel = computed(() => {
  const value = Number(props.image?.bit_depth || 0)
  return value > 0 ? `${value}-bit` : '-'
})
const colorProfileLabel = computed(() => props.image?.color_profile || '-')
const uploadedAt = computed(() => (props.image?.created_at ? new Date(props.image.created_at).toLocaleString() : '-'))
const originalExtension = computed(() => getFilenameExtension(props.image?.original_filename || props.image?.filename || ''))

function getFilenameExtension(filename) {
  const clean = (filename || '').trim()
  const dotIndex = clean.lastIndexOf('.')
  return dotIndex > 0 && dotIndex < clean.length - 1 ? clean.slice(dotIndex).toLowerCase() : ''
}

function syncForm() {
  const image = props.image
  if (!image) {
    return
  }
  Object.assign(form, {
    original_filename: image.original_filename || '',
    artist_name: image.artist_name || '',
    source_url: image.source_url || '',
    rating: image.rating || 'safe',
    is_public: image.is_public ?? true,
    favorite_count: image.favorite_count ?? 0
  })
}

function close() {
  if (!saving.value) {
    emit('close')
  }
}

function payload() {
  return {
    original_filename: form.original_filename,
    artist_name: form.artist_name,
    source_url: form.source_url,
    rating: form.rating,
    is_public: form.is_public,
    favorite_count: form.favorite_count
  }
}

function validateFilename() {
  const filename = form.original_filename.trim()
  if (!filename) {
    return true
  }
  const nextExtension = getFilenameExtension(filename)
  if (originalExtension.value && nextExtension !== originalExtension.value) {
    ElMessage.warning(`文件后缀必须保持为 ${originalExtension.value}`)
    return false
  }
  if (!originalExtension.value && nextExtension) {
    ElMessage.warning('原文件没有后缀，不能新增后缀')
    return false
  }
  return true
}

async function save() {
  if (!props.image?.id) {
    return
  }
  if (!validateFilename()) {
    return
  }
  saving.value = true
  try {
    const updated = await galleryApi.updateImage(props.image.id, payload())
    ElMessage.success('已保存')
    emit('saved', updated)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    close()
  }
}

function lockScroll() {
  previousHtmlOverflow = document.documentElement.style.overflow
  previousBodyOverflow = document.body.style.overflow
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
}

function restoreScroll() {
  document.documentElement.style.overflow = previousHtmlOverflow
  document.body.style.overflow = previousBodyOverflow
}

watch(() => props.image, syncForm, { immediate: true })

onMounted(() => {
  lockScroll()
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  restoreScroll()
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div class="image-detail-overlay" @click.self="close">
      <div class="image-detail-overlay__panel admin-image-edit-overlay-panel" @click.stop>
        <el-button class="image-detail-overlay__close" circle :icon="Close" aria-label="关闭" @click="close" />

        <div class="detail-layout admin-image-edit-view">
          <div class="detail-panel admin-image-edit-preview">
            <ResponsiveImage
              :image="image"
              :alt="title"
              img-class="detail-image"
              variant="preview"
              prefer-hdr
              prefer-animated
            />
          </div>

          <aside class="detail-panel image-detail-meta admin-image-edit-meta">
            <h2>{{ title }}</h2>
            <div class="chip-row">
              <el-tag>{{ dimensions }}</el-tag>
              <el-tag>{{ orientationLabel(image.orientation) }}</el-tag>
              <el-tag type="success">{{ fileSize }}</el-tag>
              <el-tag :type="ratingTagType(form.rating)">{{ ratingLabel(form.rating) }}</el-tag>
              <el-tag v-if="image.dynamic_range === 'hdr'" type="warning">HDR</el-tag>
              <el-tag v-if="image.is_animated" type="info">动图</el-tag>
            </div>

            <el-descriptions :column="1" border class="admin-image-edit-facts">
              <el-descriptions-item label="MIME">{{ mimeType }}</el-descriptions-item>
              <el-descriptions-item label="显示">{{ dynamicRangeLabel }}</el-descriptions-item>
              <el-descriptions-item label="位深">{{ bitDepthLabel }}</el-descriptions-item>
              <el-descriptions-item label="色彩">{{ colorProfileLabel }}</el-descriptions-item>
              <el-descriptions-item label="上传时间">{{ uploadedAt }}</el-descriptions-item>
            </el-descriptions>

            <el-form class="admin-image-edit-form" label-width="68px" :model="form">
              <el-form-item label="文件名">
                <el-input v-model="form.original_filename" :placeholder="originalExtension ? `保持 ${originalExtension} 后缀` : '不允许新增后缀'" />
              </el-form-item>
              <el-form-item label="作者">
                <el-input v-model="form.artist_name" />
              </el-form-item>
              <el-form-item label="来源">
                <el-input v-model="form.source_url" />
              </el-form-item>
              <el-form-item label="分级">
                <el-radio-group v-model="form.rating">
                  <el-radio-button v-for="option in ratingOptions" :key="option.value" :label="option.value">
                    {{ option.label }}
                  </el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="收藏数">
                <el-input-number v-model="form.favorite_count" :min="0" />
              </el-form-item>
              <el-form-item label="公开">
                <el-switch v-model="form.is_public" active-text="公开" inactive-text="隐藏" />
              </el-form-item>
            </el-form>

            <div class="admin-image-edit-actions">
              <el-button @click="close">取消</el-button>
              <el-button type="primary" :loading="saving" @click="save">保存</el-button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </Teleport>
</template>
