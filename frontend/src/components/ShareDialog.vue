<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { galleryApi } from '../api/gallery'
import { imageShareCode, sharePageUrl } from '../utils/shareFormats'

const props = defineProps({
  images: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'created'])
const activeTab = ref('links')
const format = ref('url')
const title = ref(defaultTitle(props.images))
const expiresInHours = ref(0)
const creating = ref(false)
const share = ref(null)

const expiryOptions = [
  { label: '永久有效', value: 0 },
  { label: '1 天', value: 24 },
  { label: '7 天', value: 24 * 7 },
  { label: '30 天', value: 24 * 30 }
]

const containsRestrictedImage = computed(() => props.images.some((image) => !image.is_public || image.rating === 'hidden'))
const ordinaryCode = computed(() => imageShareCode(props.images, format.value))
const authorizedCode = computed(() => (
  share.value ? imageShareCode(props.images, format.value, share.value.token) : ''
))
const albumUrl = computed(() => (share.value ? sharePageUrl(share.value.token) : ''))
const shareExpiryLabel = computed(() => {
  if (!share.value) return ''
  return share.value.expires_at
    ? `有效至 ${new Date(share.value.expires_at).toLocaleString()}`
    : '永久有效'
})

function defaultTitle(images) {
  return '图片分享'
}

async function copy(value, message = '已复制') {
  if (!value) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    ElMessage.success(message)
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function copyOrdinaryCode() {
  if (containsRestrictedImage.value) {
    ElMessage.warning('所选内容含非公开或隐藏图片，请使用相册分享链接')
    return
  }
  await copy(ordinaryCode.value, format.value === 'url' ? '已复制链接' : '已复制代码')
}

async function createAlbumShare() {
  if (creating.value || !props.images.length) return
  creating.value = true
  try {
    share.value = await galleryApi.createShare({
      image_ids: props.images.map((image) => image.id),
      title: title.value.trim() || undefined,
      expires_in_hours: expiresInHours.value || undefined
    })
    emit('created', share.value)
    ElMessage.success('相册分享链接已生成')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '生成分享链接失败')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <el-dialog title="分享图片" :model-value="true" width="760px" destroy-on-close @close="emit('close')">
    <p class="muted share-dialog-summary">已选择 {{ images.length }} 张图片。普通图床格式使用原图直链；相册分享使用可撤销的独立访问链接。</p>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="图床链接" name="links">
        <el-alert
          v-if="containsRestrictedImage"
          type="warning"
          :closable="false"
          title="所选内容含非公开或隐藏图片；请使用“相册分享”生成带访问授权的外链。"
          show-icon
        />
        <el-radio-group v-model="format" class="share-format-selector">
          <el-radio-button label="url">URL</el-radio-button>
          <el-radio-button label="markdown">Markdown</el-radio-button>
          <el-radio-button label="bbcode">论坛 BBCode</el-radio-button>
        </el-radio-group>
        <p class="muted share-copy-hint">点击下方内容即可复制。</p>
        <el-input
          class="share-code share-copy-field"
          type="textarea"
          :rows="8"
          readonly
          title="点击复制"
          :model-value="ordinaryCode"
          @click="copyOrdinaryCode"
        />
      </el-tab-pane>

      <el-tab-pane label="相册分享" name="album">
        <el-form label-width="84px" @submit.prevent>
          <el-form-item label="分享标题">
            <el-input v-model="title" maxlength="255" show-word-limit />
          </el-form-item>
          <el-form-item label="有效期">
            <el-select v-model="expiresInHours" style="width: 180px">
              <el-option v-for="option in expiryOptions" :key="option.label" :label="option.label" :value="option.value" />
            </el-select>
          </el-form-item>
        </el-form>
        <p class="muted">单图会生成单图分享页，多图会生成按当前选择顺序展示的相册页。达到有效期或撤销后，页面及带授权的嵌入链接会立即失效。</p>
        <div v-if="share" class="share-generated-result">
          <p class="muted share-copy-hint">{{ shareExpiryLabel }}，点击链接或嵌入代码即可复制。</p>
          <el-input
            class="share-copy-field"
            readonly
            title="点击复制相册链接"
            :model-value="albumUrl"
            @click="copy(albumUrl, '已复制相册链接')"
          />
          <el-radio-group v-model="format" class="share-format-selector">
            <el-radio-button label="url">URL</el-radio-button>
            <el-radio-button label="markdown">Markdown</el-radio-button>
            <el-radio-button label="bbcode">论坛 BBCode</el-radio-button>
          </el-radio-group>
          <el-input
            class="share-code share-copy-field"
            type="textarea"
            :rows="7"
            readonly
            title="点击复制嵌入代码"
            :model-value="authorizedCode"
            @click="copy(authorizedCode, '已复制带授权的嵌入代码')"
          />
          <div class="share-dialog-actions">
            <el-button type="primary" tag="a" :href="albumUrl" target="_blank" rel="noreferrer">打开分享页</el-button>
          </div>
        </div>
        <div v-else class="share-dialog-actions">
          <el-button type="primary" :loading="creating" @click="createAlbumShare">生成相册分享链接</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>
