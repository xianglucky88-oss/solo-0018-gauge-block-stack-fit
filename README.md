# 量块组合公差计算

虚拟测量工位工程师提交合成量块清单、证书生效区间和目标公差。服务输出指定组合的保守校正区间，或比较候选组合的块数和公差裕量。不是实际设备的校准或认证软件。

## 运行

Python 3.11 或以上，仅标准库。切换到此仓库目录。

```sh
python3 -B -m gauge.http_api --port 8745
curl --json @examples/demo.json http://127.0.0.1:8745/stackfit/conforming-stacks
```

不常驻启动也可运行以下演示；每次使用临时本机端口，结束后释放。

```sh
python3 -B -m gauge.example /stackfit/certificate-status
python3 -B -m gauge.example /stackfit/stack-interval
python3 -B -m gauge.example /stackfit/conforming-stacks
```

参见 [领域规则与接口](PROJECT_SPEC.md)。`examples/demo.json` 为完整合成输入；其他示例用于观察拒收或待核。业务单元测试留待后续，当前不假设联网、数据库或已有用户数据。

## 装夹约束（在位改配 / 停台重组）

`conforming-stacks` 请求可选带 `fixture`，把工位拆成夹在基座的锁定块与当前可拆块：

- `locked`：不可拆的块，必须全部保留在在位方案中。
- `mounted`：当前在装的全部块（包含 `locked`）。
- `stoppage_only`：停台后才能领取的替换块，只允许进入停台单据。
- `max_changes`：现场允许的最大拆加次数，拆一块、加一块各计一次。

响应分成两份可按当日证书复核的单据：`in_place`（保留全部锁定块、不超限的在位改配，按实际拆加次数优先、再按 `rank` 偏好排序，并附预算内裕量最大的备选）与 `stoppage`（对当日全部有效证书块自由重组，附裕量最大的停台备选）。若没有在位方案，`in_place.blocked_reason` 明确给出 `fixture_constraint`（装夹或拆加次数限制）或 `retained_certificate_unavailable`（原保留块唯一证书当日无效）。三个合成场景：

```sh
python3 -B -m gauge.example /stackfit/conforming-stacks --input examples/fixture-in-place.json
python3 -B -m gauge.example /stackfit/conforming-stacks --input examples/fixture-stoppage-clamp.json
python3 -B -m gauge.example /stackfit/conforming-stacks --input examples/fixture-stoppage-cert.json
```

不带 `fixture` 的请求与基线完全一致。
