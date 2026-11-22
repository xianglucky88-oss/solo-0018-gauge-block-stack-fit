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

## 单块备用块的采购/计量对照

`analysis/` 用同一组 HTTP 入口回答"单块备用量块先下单还是等投产日"。场景、两个候选投产日和一张只改证书生效日的对照都在 `analysis/scenario.json`；结论见 [采购说明](analysis/PROCUREMENT_DECISION.md) 与 [计量说明](analysis/METROLOGY_DECISION.md)。

```sh
python3 -B -m analysis.run_decision_matrix
```

生成 `analysis/out/decision_matrix.json` 和可逐案复跑的 `analysis/out/inputs/`。只改单块证书生效日时，原可先下单的方案会转为等日期；同一备用块可在两个日期搭配不同在库块的例子也保留在同一份对照中。
