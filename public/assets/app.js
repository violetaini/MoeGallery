const dropzones = document.querySelectorAll('.dropzone');

dropzones.forEach((zone) => {
  zone.addEventListener('dragover', (event) => {
    event.preventDefault();
    zone.classList.add('is-dragging');
  });

  zone.addEventListener('dragleave', () => {
    zone.classList.remove('is-dragging');
  });

  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    zone.classList.remove('is-dragging');
    const input = zone.querySelector('input[type="file"]');
    if (input && event.dataTransfer.files.length > 0) {
      input.files = event.dataTransfer.files;
    }
  });
});
