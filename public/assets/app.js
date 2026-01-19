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

document.querySelectorAll('[data-dialog-target]').forEach((trigger) => {
  trigger.addEventListener('click', () => {
    const selector = trigger.getAttribute('data-dialog-target');
    const dialog = selector ? document.querySelector(selector) : null;
    if (dialog && typeof dialog.showModal === 'function') {
      dialog.showModal();
    }
  });
});

document.querySelectorAll('[data-dialog-close]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const dialog = btn.closest('dialog');
    if (dialog) {
      dialog.close();
    }
  });
});
