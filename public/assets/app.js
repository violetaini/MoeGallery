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

document.querySelectorAll('[data-modal-target]').forEach((trigger) => {
  trigger.addEventListener('click', () => {
    const selector = trigger.getAttribute('data-modal-target');
    const modal = selector ? document.querySelector(selector) : null;
    if (modal) {
      modal.classList.add('open');
    }
  });
});

document.querySelectorAll('[data-modal-close]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const modal = btn.closest('.share-modal');
    if (modal) {
      modal.classList.remove('open');
    }
  });
});

document.querySelectorAll('.share-modal').forEach((modal) => {
  modal.addEventListener('click', (event) => {
    if (event.target === modal) {
      modal.classList.remove('open');
    }
  });
});

document.querySelectorAll('.share-link').forEach((container) => {
  const input = container.querySelector('.share-input input');
  const url = container.getAttribute('data-share-url') || '';
  const formats = {
    url,
    html: `<img src=\"${url}\" alt=\"image\">`,
    bbcode: `[img]${url}[/img]`,
    markdown: `![image](${url})`,
  };
  container.querySelectorAll('.share-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      container.querySelectorAll('.share-tab').forEach((btn) => {
        btn.classList.remove('active');
      });
      tab.classList.add('active');
      const format = tab.getAttribute('data-format') || 'url';
      if (input) {
        input.value = formats[format] || url;
      }
    });
  });
});
