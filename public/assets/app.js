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

const rocketButton = document.querySelector('.floating-rocket');
const rocketHiddenKey = 'rocketHidden';
if (rocketButton) {
  const applyState = (hidden) => {
    rocketButton.classList.toggle('collapsed', hidden);
    rocketButton.setAttribute(
      'aria-label',
      hidden ? '展开返回按钮' : '返回上一级'
    );
  };
  const storedHidden = localStorage.getItem(rocketHiddenKey) === 'true';
  applyState(storedHidden);

  rocketButton.addEventListener('click', () => {
    if (rocketButton.classList.contains('collapsed')) {
      localStorage.setItem(rocketHiddenKey, 'false');
      applyState(false);
      return;
    }
    window.history.back();
  });

  rocketButton.addEventListener('contextmenu', (event) => {
    event.preventDefault();
    const nextHidden = !rocketButton.classList.contains('collapsed');
    localStorage.setItem(rocketHiddenKey, String(nextHidden));
    applyState(nextHidden);
  });
}
