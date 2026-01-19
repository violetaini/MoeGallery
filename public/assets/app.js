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

document.querySelectorAll('.user-chip').forEach((chip) => {
  const trigger = chip.querySelector('.user-menu-trigger');
  const menu = chip.querySelector('.user-menu');
  if (!trigger || !menu) {
    return;
  }
  trigger.addEventListener('click', () => {
    const isOpen = menu.classList.toggle('open');
    trigger.setAttribute('aria-expanded', String(isOpen));
  });
  document.addEventListener('click', (event) => {
    if (!chip.contains(event.target)) {
      menu.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
    }
  });
});

const backButton = document.querySelector('.floating-back');
if (backButton) {
  backButton.addEventListener('click', () => {
    window.history.back();
  });
}
