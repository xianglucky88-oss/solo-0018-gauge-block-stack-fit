import {json} from './api.js';

export function populate(select, items, preferred) {
  const previous = select.value;
  select.replaceChildren(...items.map(([id, label]) => new Option(label, id)));
  if (items.some(([id]) => id === previous)) select.value = previous;
  else if (preferred !== undefined) select.value = preferred;
}

export function mountRevisions(ui, metadata, renderComparison) {
  const list = document.querySelector('#events');
  const before = document.querySelector('#before');
  const after = document.querySelector('#after');
  const operation = document.querySelector('#compare-operation');
  let lastHead;
  populate(operation, metadata.operations.map((op) => [op.id, op.label]));
  document.querySelector('#compare-form').addEventListener('submit', (event) => {
    event.preventDefault();
    ui.perform(async () => {
      if (!before.value || !after.value) throw new Error('请选择两个已发布版本');
      renderComparison(await json('/api/compare', {dataset: ui.name(), before: before.value, after: after.value, operation: operation.value}));
    });
  });

  return (history, switched) => {
    document.querySelector('#head').textContent = history.head.revision
      ? `第 ${history.head.generation} 代 · ${history.head.revision.slice(0, 12)}` : '尚未发布';
    const versions = history.versions.map((v) => [v.id, `${v.id.slice(0, 12)} · ${v.source}`]);
    if (switched || lastHead !== history.head.revision) {
      before.selectedIndex = after.selectedIndex = -1;
      renderComparison(null);
    }
    lastHead = history.head.revision;
    populate(before, versions, versions.find(([id]) => id !== history.head.revision)?.[0]);
    populate(after, versions, history.head.revision ?? undefined);
    const seen = new Set();
    list.replaceChildren(...history.events.map((event) => {
      const row = document.createElement('li');
      row.textContent = `第 ${event.generation} 代 · ${event.action === 'restore' ? '恢复' : '发布'} · ${event.revision.slice(0, 12)}`;
      if (!seen.has(event.revision) && event.revision !== history.head.revision) {
        const button = document.createElement('button');
        button.textContent = '恢复为当前';
        button.addEventListener('click', () => ui.perform(async () => {
          await json('/api/restore', {dataset: history.dataset, revision: event.revision, generation: history.head.generation});
          await ui.refresh();
        }));
        row.append(button);
      }
      seen.add(event.revision);
      return row;
    }));
  };
}
