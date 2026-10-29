document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!form.dataset.autoSubmit && !window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const startForm = document.querySelector('#start-form');
if (startForm) {
  const scope = JSON.parse(document.querySelector('#scope-data').textContent);
  const count = document.querySelector('#count');
  const custom = document.querySelector('#custom-count');
  const restart = startForm.querySelector('[name=restart]');
  const update = () => {
    const selected = [...startForm.querySelectorAll('[name=categories]:checked')].map(input => input.value);
    const kinds = [...startForm.querySelectorAll('[name=kinds]:checked')].map(input => input.value);
    const subcategory = startForm.querySelector('[name=subcategory]').value;
    const mode = startForm.querySelector('[name=mode]:checked').value;
    const sequential = mode === 'sequential';
    const exam = mode === 'exam';
    count.querySelector('[value="0"]').disabled = !sequential;
    if (!sequential && count.value === '0') count.value = exam ? '50' : '20';
    restart.disabled = !sequential;
    if (!sequential) restart.checked = false;
    document.querySelector('#restart-field').hidden = !sequential;
    const isCustom = count.value === 'custom';
    custom.closest('label').hidden = !isCustom;
    custom.disabled = !isCustom;
    custom.required = isCustom;
    custom.max = exam ? '300' : '10000';
    custom.name = isCustom ? 'count' : '';
    count.name = isCustom ? '' : 'count';
    document.querySelector('#selection-count').textContent = `已选择 ${selected.length} 个板块`;
    const rows = scope.filter(row => selected.includes(row.category) && (!kinds.length || kinds.includes(row.kind)) && (!subcategory || row.category !== 'auto' || row.subcategory === subcategory) && (!exam || row.kind !== 'short'));
    const total = rows.reduce((sum, row) => sum + row.total, 0);
    const done = rows.reduce((sum, row) => sum + row.done, 0);
    const mastered = rows.reduce((sum, row) => sum + row.mastered, 0);
    document.querySelector('#available-count').textContent = total;
    document.querySelector('#coverage-text').textContent = `本轮已练 ${done} / ${total} 题，剩余 ${total - done} 题`;
    document.querySelector('#coverage-progress').max = total || 1;
    document.querySelector('#coverage-progress').value = done;
    document.querySelector('#coverage-complete').hidden = !total || done < total;
    document.querySelector('#mastery-text').textContent = `已掌握 ${mastered} 题。客观题连续三次答对后减少出题，简答题按自评标记。`;
    document.querySelector('#mode-help').textContent = {
      sequential: '顺序练习跳过本轮已答题，选“全部未练题”即可一次创建剩余题目。',
      random: '随机练习打乱所选范围的题目，不按掌握状态调整频率。',
      review: '未练题优先；练过的题中错题优先、普通题正常安排、已掌握题少量抽查。单次不重复，错题本仍由你手动管理。',
      exam: '模拟练习每次 1—300 题，只含客观题，按原规则抽题，不受掌握状态影响。'
    }[mode];
  };
  startForm.addEventListener('change', event => {
    if (event.target.name === 'mode') count.value = event.target.value === 'exam' ? '50' : '20';
    update();
  });
  startForm.addEventListener('submit', event => {
    if (!startForm.querySelector('[name=categories]:checked')) {
      event.preventDefault();
      window.alert('请至少选择一个学习板块。');
    } else if (restart.checked && !window.confirm('重新通刷所选范围？本轮进度将重置，历史记录、掌握状态和错题保留。')) {
      event.preventDefault();
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
