document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!form.dataset.autoSubmit && !window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const startForm = document.querySelector('#start-form');
if (startForm) {
  const boards = JSON.parse(document.querySelector('#board-data').textContent);
  const count = document.querySelector('#count');
  const update = () => {
    const selected = [...startForm.querySelectorAll('[name=categories]:checked')].map(input => input.value);
    document.querySelector('#selection-count').textContent = `已选择 ${selected.length} 个板块`;
    document.querySelector('#available-count').textContent = boards.filter(board => selected.includes(board.key)).reduce((sum, board) => sum + board.count, 0);
  };
  startForm.addEventListener('change', event => {
    update();
    if (event.target.name === 'mode') count.value = event.target.value === 'exam' ? 50 : 20;
  });
  startForm.addEventListener('submit', event => {
    if (!startForm.querySelector('[name=categories]:checked')) {
      event.preventDefault();
      window.alert('请至少选择一个学习板块。');
    }
  });
  update();
}

const timer = document.querySelector('[data-deadline]');
if (timer) {
  const started = performance.now();
  const seconds = Number(timer.dataset.remaining);
  let submitted = false;
  const tick = () => {
    const remaining = Math.max(0, Math.ceil(seconds - (performance.now() - started) / 1000));
    document.querySelector('#countdown').textContent = `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`;
    if (!remaining && !submitted) {
      submitted = true;
      const form = document.querySelector('#finish-form');
      form.dataset.autoSubmit = 'true';
      form.requestSubmit();
    }
  };
  tick();
  setInterval(tick, 1000);
}

if (window.matchMedia('(max-width:800px)').matches) {
  const card = document.querySelector('.answer-card');
  if (card) card.open = false;
}
