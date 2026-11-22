import {json, request} from './api.js';

export function mountIntake(ui) {
  const form = document.querySelector('#intake-form');
  const source = document.querySelector('#source');
  const input = document.querySelector('#input');
  const upload = document.querySelector('#upload');
  const note = document.querySelector('#draft-note');
  const drafts = document.querySelector('#drafts');
  let original;

  function load(text, name) {
    input.value = text;
    original = {text, displayed: input.value};
    source.value = name;
  }

  upload.addEventListener('change', () => ui.perform(async () => {
    const file = upload.files[0];
    upload.value = '';
    if (!file) return;
    if (file.size > 262144) throw new Error('原料须在 256 KiB 以内');
    const bytes = await file.arrayBuffer();
    try {
      load(new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes), file.name);
    } catch {
      throw new Error('文件不是有效 UTF-8');
    }
  }));
  document.querySelector('#sample').addEventListener('click', () => ui.perform(async () => {
    load(await (await request('/example.json')).text(), 'workbench.json');
  }));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    ui.perform(async () => {
      const text = original?.displayed === input.value ? original.text : input.value;
      const draft = await json('/api/stage', {dataset: ui.name(), source: source.value, text});
      await ui.refresh();
      note.textContent = ({ready: '校验通过，等待发布', published: '此暂存单已发布', rejected: '校验未通过'})[draft.state];
    });
  });

  return (history, switched) => {
    if (switched) {
      form.reset();
      original = undefined;
      note.replaceChildren();
    }
    drafts.replaceChildren(...history.drafts.map((draft) => {
      const row = document.createElement('li');
      const label = document.createElement('span');
      label.textContent = `${draft.source} · 第 ${draft.base} 代 · ${draft.state === 'ready' ? '待发布' : '未通过'}`;
      row.append(label);
      if (draft.reason) row.append(`（${draft.reason}）`);
      if (draft.state === 'ready' && draft.base === history.head.generation) {
        const button = document.createElement('button');
        button.textContent = '发布';
        button.addEventListener('click', () => ui.perform(async () => {
          await json('/api/publish', {draft: draft.id});
          await ui.refresh();
          note.textContent = '版本已发布';
        }));
        row.append(button);
      } else if (draft.state === 'ready') row.append('（已过期）');
      return row;
    }));
  };
}
