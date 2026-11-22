import {json} from './api.js';
import {populate} from './revisions.js';

const labels = {state: '结果状态', refs: '出处数', pending: '待核项', transcription: '转写内容', provenance: '出处条目',
  segments: '分段数', alternatives: '校准方案数', candidates: '候选数', years: '年份条数', rows: '数据条数',
  feasible_count: '合规方案数', gap_count: '断档数', changed_count: '变化项', matches: '复算一致',
  on: '查询日期', total: '合计', accepted: '是否通过', windows: '时段数', disposition: '结论'};

function payload(value) {
  const fragment = document.createDocumentFragment();
  const facts = document.createElement('dl');
  facts.className = 'facts';
  for (const [key, item] of Object.entries(value ?? {})) {
    if (!(key in labels)) continue;
    if (!Array.isArray(item) && item !== null && typeof item === 'object') continue;
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = labels[key];
    description.textContent = Array.isArray(item) ? `${item.length} 项` : typeof item === 'boolean' ? (item ? '是' : '否') : String(item).slice(0, 300);
    facts.append(term, description);
  }
  if (facts.childNodes.length) fragment.append(facts);
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = '查看完整 JSON';
  const pre = document.createElement('pre'); pre.textContent = JSON.stringify(value, null, 2);
  details.append(summary, pre);
  fragment.append(details);
  return fragment;
}

export function showComparison(data) {
  const root = document.querySelector('#comparison');
  if (data === null) {
    root.replaceChildren();
    return;
  }
  const text = document.createElement('p');
  text.textContent = data.output_changed ? '两个版本产出不同' : '两个版本产出一致';
  root.replaceChildren(text, payload(data));
}

export function mountResults(ui, metadata) {
  const runs = document.querySelector('#runs');
  const selection = document.querySelector('#run-revision');
  const choices = document.querySelector('#operations');
  const names = new Map(metadata.operations.map((op) => [op.id, op.label]));
  choices.replaceChildren(...metadata.operations.map((op, i) => {
    const label = document.createElement('label');
    const input = document.createElement('input'); input.type = 'checkbox'; input.value = op.id; input.checked = i === 0;
    label.append(input, op.label);
    return label;
  }));

  function show(item, dataset) {
    const article = document.createElement('details');
    article.className = 'run'; article.open = true;
    const title = document.createElement('summary'); title.textContent = `${names.get(item.operation)} · ${dataset} · ${item.revision.slice(0, 12)}`;
    const bar = document.createElement('div'); bar.className = 'run-actions';
    const output = document.createElement('span'); output.setAttribute('role', 'status');
    const replay = document.createElement('button'); replay.textContent = '复算';
    replay.addEventListener('click', () => ui.perform(async () => {
      const check = await json('/api/replay', {run: item.id});
      output.textContent = check.matches ? '与历史结果一致' : '与历史结果不一致';
    }));
    const download = document.createElement('a'); download.href = `/api/evidence/${item.id}`; download.textContent = '导出证据';
    bar.append(replay, download, output);
    article.append(title, bar, payload(item.output));
    return article;
  }

  document.querySelector('#run-form').addEventListener('submit', (event) => {
    event.preventDefault();
    ui.perform(async () => {
      const dataset = ui.name();
      const operations = Array.from(choices.querySelectorAll(':checked'), (input) => input.value);
      const batch = await json('/api/run', {dataset, operations, revision: selection.value || null});
      runs.replaceChildren(...batch.runs.map((run) => show(run, dataset)));
    });
  });
  return (history, switched) => {
    if (switched) runs.replaceChildren();
    populate(selection, [['', '当前发布版本'], ...history.versions.map((v) => [v.id, v.id.slice(0, 12)])]);
  };
}
