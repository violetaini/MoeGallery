export const imageLoadingPlaceholders = {
  landscape: '/placeholder/image-loading-landscape.webp',
  portrait: '/placeholder/image-loading-portrait.webp'
}

export function imagePlaceholderFor(image) {
  if (image?.orientation === 'portrait') {
    return imageLoadingPlaceholders.portrait
  }
  if (image?.orientation === 'landscape' || image?.orientation === 'square') {
    return imageLoadingPlaceholders.landscape
  }
  if (image?.width && image?.height && image.height > image.width) {
    return imageLoadingPlaceholders.portrait
  }
  return imageLoadingPlaceholders.landscape
}
