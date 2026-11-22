# 量块组合公差计算

虚拟测量工位工程师提交合成量块清单、证书生效区间和目标公差。服务输出指定组合的保守校正区间，或比较候选组合的块数和公差裕量。不是实际设备的校准或认证软件。

## 运行

Python 3.11 或以上，仅标准库。切换到此仓库目录。

```sh
python3 -B -m gauge.http_api --port 8745
curl --json @examples/demo.json http://127.0.0.1:8745/stackfit/conforming-stacks
curl --json @examples/shared_reservation.json \
  http://127.0.0.1:8745/stackfit/shared-reservation
```

不常驻启动也可运行以下演示；每次使用临时本机端口，结束后释放。

```sh
python3 -B -m gauge.example /stackfit/certificate-status
python3 -B -m gauge.example /stackfit/stack-interval
python3 -B -m gauge.example /stackfit/conforming-stacks
```

共享盒预留（`/stackfit/shared-reservation`）的输入含 `first_task`（已承诺开工侧）
和恰好两个 `branches`（第二侧的两种公差任务），块目录与证书规则不变。输出：

- `robust_reservations`：可提前承诺的首单组合（同一组块对两个分支都成立），
  按最坏分支较小双侧裕量降序、同分按最坏分支同时用块总数、首单块数与稳定标识排序；
  每条给出两个分支各自在剩余块上的第二侧单。分支单互斥，可同名块，但与首单永不相交。
- `wait_and_see`：假设能等第二侧确认再出首单时，逐分支的最佳联合方案，以及
  `non_reservable_first_orders`——能同时开工却无法提前预留的首单及被卡分支。
- 无任何首单能同时覆盖两分支时 `state` 为 `no_robust_reservation`。

单元测试：

```sh
python3 -B -m unittest discover -s tests
```

参见 [领域规则与接口](PROJECT_SPEC.md)。`examples/demo.json` 为完整合成输入；其他示例用于观察拒收或待核。业务单元测试留待后续，当前不假设联网、数据库或已有用户数据。
