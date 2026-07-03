export const supportedImageUploadExtensions = [
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.gif',
  '.bmp',
  '.tif',
  '.tiff',
  '.heif',
  '.heic',
  '.avif',
  '.jxr'
]

export const imageUploadAccept = supportedImageUploadExtensions.join(',')

export const imageUploadSupportText = supportedImageUploadExtensions.join(' ')
