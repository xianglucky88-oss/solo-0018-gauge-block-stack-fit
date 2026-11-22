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

台阶用块卡与单块证书半径对照：

```sh
python3 -B -m gauge.example /stackfit/step-card --input examples/step-card.json
python3 -B -m gauge.example /stackfit/step-card --input examples/step-broken.json
python3 -B -m gauge.example /stackfit/step-card --input examples/step-unreachable.json
python3 -B -m gauge.example /stackfit/step-counterexample --input examples/step-counterexample.json
```

`step-card` 把 2~4 个严格递增的目标区间安排到同一叠量块上：每级列出新增实体块，各级校正区间与裕量来自同一次证书裁决；排名先让最差一级裕量最大，其次整叠用块更少，完全并列按稳定标识顺序。无法装配时区分单级不可达与断链，后者给出最长连续前缀和下一关的限制证据。`step-counterexample` 在相同目标下只改一块的合法证书半径，使各高度仍能各自满足而整叠不再可装，只返回推荐和断点证据。

参见 [领域规则与接口](PROJECT_SPEC.md)。`examples/demo.json` 为完整合成输入；其他示例用于观察拒收或待核。业务单元测试留待后续，当前不假设联网、数据库或已有用户数据。
