import {json} from './api.js';

const states = {open: '待复核', approved: '已通过', returned: '已退回'};

export function reviewControls(ui, item, opening) {
  const root = document.createElement('div');
  root.className = 'run-actions';
  const button = (label, action) => {
    const node = document.createElement('button');
    node.type = 'button'; node.textContent = label;
    node.addEventListener('click', () => ui.perform(action));
    return node;
  };
  const update = async () => {
    const {cases} = await json('/api/review/history', {run: item.id});
    root.replaceChildren(button('新增复核', async () => {
      await json('/api/review/open', {run: item.id, generation: opening});
      await update();
    }));
    for (const entry of cases) {
      const row = document.createElement('div');
      row.className = 'run-actions';
      const status = document.createElement('span');
      status.textContent = `第 ${entry.generation} 代 · ${states[entry.state]}${entry.eligible ? '' : ' · 不满足领域放行条件'}`;
      row.append(status);
      if (entry.state === 'open') {
        const decide = (decision) => async () => {
          await json('/api/review/decide', {review: entry.id, decision});
          await update();
        };
        if (entry.eligible) row.append(button('通过复核', decide('approved')));
        row.append(button('退回复核', decide('returned')));
      }
      if (entry.state === 'approved') {
        if (entry.dispatched) {
          const link = document.createElement('a');
          link.href = `/api/dispatch/${entry.id}`;
          link.textContent = '下载交接凭据';
          row.append(link);
        } else {
          row.append(button('签发交接', async () => {
            await json('/api/dispatch', {review: entry.id});
            await update();
          }));
        }
      }
      root.append(row);
    }
  };
  root.append(button('查看复核交接', update));
  return root;
}
