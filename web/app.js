import {json} from './api.js';
import {mountIntake} from './intake.js';
import {mountRevisions} from './revisions.js';
import {mountResults, showComparison} from './results.js';

const form = document.querySelector('#dataset-form');
const field = document.querySelector('#dataset');
const status = document.querySelector('#status');
let current;
let busy = false;
let render = [];

async function perform(action) {
  if (busy) return;
  busy = true;
  const buttons = Array.from(document.querySelectorAll('button:not(:disabled)'));
  for (const button of buttons) button.disabled = true;
  status.removeAttribute('data-error');
  status.textContent = '处理中…';
  try {
    await action();
    status.textContent = '';
  } catch (error) {
    status.setAttribute('data-error', '');
    status.textContent = error instanceof Error ? error.message : '操作未完成';
  } finally {
    for (const button of buttons) button.disabled = false;
    busy = false;
  }
}

async function load(name) {
  const history = await json('/api/history', {dataset: name});
  const switched = current !== name;
  current = name;
  for (const draw of render) draw(history, switched);
}

const ui = {perform, refresh: () => load(current), name: () => current};
form.addEventListener('submit', (event) => {
  event.preventDefault();
  perform(() => load(field.value));
});

perform(async () => {
  const meta = await json('/api/meta');
  document.documentElement.dataset.theme = meta.theme;
  document.title = document.querySelector('#title').textContent = meta.title;
  document.querySelector('#work-label').textContent = meta.work_label;
  field.value = meta.example_dataset;
  render = [mountIntake(ui), mountRevisions(ui, meta, showComparison), mountResults(ui, meta)];
  await load(field.value);
});
