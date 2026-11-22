const messages = {
  invalid_json: 'JSON 无效或有重复字段', domain_input: '原料不符合业务规则',
  generation_conflict: '当前版本已变化，请重新载入；暂存单需重新导入',
  no_published_revision: '数据集还没有发布版本', operation_selection: '请选择至少一个加工项目',
  draft_rejected: '未通过校验的原料不能发布', database_busy: '数据库正忙，请稍后重试',
  input_size: '原料须在 256 KiB 以内', source_name: '来源文件名无效',
  revision_wrong_dataset: '版本不属于该数据集', network: '无法连接本机服务',
};

export async function request(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
  } catch {
    throw new Error(messages.network);
  }
  if (!response.ok) {
    const fault = await response.json().catch(() => ({}));
    const reason = messages[fault.error] ?? `请求未完成（${response.status}）`;
    throw new Error(fault.detail ? `${reason}：${fault.detail}` : reason);
  }
  return response;
}

export async function json(path, body) {
  return (await request(path, body)).json();
}
