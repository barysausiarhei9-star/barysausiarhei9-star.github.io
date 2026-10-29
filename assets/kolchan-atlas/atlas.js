/* Native scrolling with optional scene highlights and keyboard-accessible zoom. */
(() => {
  'use strict';
  const root = document.querySelector('.atlas-page');
  if (!root) return;
  const scenes = [...root.querySelectorAll('.atlas-scene')];
  const steps = [...root.querySelectorAll('.atlas-step')];
  const links = [...root.querySelectorAll('.atlas-scenes a')];
  const languages = [...root.querySelectorAll('.languages a')];
  const dialog = root.querySelector('.atlas-dialog');
  let active = -1;
  let queued = false;
  let opener;

  function activate(index) {
    if (index === active) return;
    active = index;
    const sceneIndex = Math.floor(index / 3);
    steps.forEach((step, n) => step.classList.toggle('is-active', n === index));
    scenes.forEach((scene, n) => {
      scene.classList.toggle('is-active', n === sceneIndex);
      scene.querySelector('.atlas-count').textContent = `${n === sceneIndex ? index % 3 + 1 : 1} / 3`;
    });
    links.forEach((link, n) => {
      if (n === sceneIndex) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    const spot = scenes[sceneIndex].querySelector('.atlas-spot');
    spot.style.setProperty('--x', `${steps[index].dataset.x}%`);
    spot.style.setProperty('--y', `${steps[index].dataset.y}%`);
    languages.forEach(link => { link.hash = `scene-${sceneIndex}`; });
  }

  function update() {
    queued = false;
    const center = innerHeight * .5;
    let nearest = 0;
    let distance = Infinity;
    steps.forEach((step, index) => {
      const box = step.getBoundingClientRect();
      const d = center < box.top ? box.top - center : center > box.bottom ? center - box.bottom : 0;
      if (d < distance) { distance = d; nearest = index; }
    });
    activate(nearest);
  }

  root.classList.add('atlas-enhanced');
  root.querySelectorAll('.atlas-controls').forEach(control => { control.hidden = false; });
  root.querySelectorAll('[data-move]').forEach(button => {
    const sceneIndex = scenes.indexOf(button.closest('.atlas-scene'));
    const direction = Number(button.dataset.move);
    button.addEventListener('click', () => {
      const current = Math.floor(active / 3) === sceneIndex ? active : sceneIndex * 3;
      const next = Math.max(0, Math.min(steps.length - 1, current + direction));
      activate(next);
      steps[next].scrollIntoView({ block: 'center', behavior: 'instant' });
      steps[next].focus({ preventScroll: true });
    });
  });
  addEventListener('scroll', () => {
    if (!queued) { queued = true; requestAnimationFrame(update); }
  }, { passive: true });
  addEventListener('resize', update);
  if (typeof dialog.showModal === 'function') {
    root.querySelectorAll('.atlas-zoom').forEach(link => {
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        opener = link;
        const image = link.querySelector('img');
        const enlarged = dialog.querySelector('img');
        enlarged.src = image.src;
        enlarged.alt = image.alt;
        dialog.showModal();
      });
    });
    dialog.querySelector('button').addEventListener('click', () => dialog.close());
    dialog.addEventListener('keydown', event => {
      if (event.key === 'Tab') {
        event.preventDefault();
        dialog.querySelector('button').focus();
      }
    });
    dialog.addEventListener('close', () => { opener?.focus({ preventScroll: true }); });
  }
  update();
})();
