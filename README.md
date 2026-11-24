# 量块组合公差工作台

原生 HTML、CSS 和 JavaScript 工作台，业务计算由 Python 完成，使用本机 SQLite 持久化。无需安装前端依赖。仅用于本地合成样本，不对公网开放。

```sh
python3 -B -m workbench
```

浏览器打开命令输出的地址（默认 `http://127.0.0.1:8818`）。工作台支持样例与文件导入、发布历史、指定版本加工、对比、复算和证据导出。可用 `--port`、`--db` 指定本机端口和数据库文件。

新增领域加工：跨日组合复验、固定组合证书账、证书有效期分段。流程验收：`python3 -B examples/workbench_check.py`。

### 同日组块差值

在工作台运行 `stack-delta`。在同一证书裁决日比较两个虚拟配置，抵消共用实体项，并分别给出绝对区间与差值区间。演练：`python3 -B examples/workbench_check.py stack-delta`。

### 同日换型链核验

在工作台运行 `change-chain`。逐步核对虚拟换型的差值限，并独立用首尾实体算净差。演练：`python3 -B examples/workbench_check.py change-chain`。

### 换证差值与复测核对

在工作台运行 `certificate-drift`。对固定组块分别查两日的独立实测与证书，将可解释换证差额和未解释残差分开报告。演练：`python3 -B examples/workbench_check.py certificate-drift`

### 补测预约按轮安排

在工作台运行 `witness-plan`。对证书区间跨过交付公差的已选组合，在下单前给出按轮可约的绝对/差长见证安排：何时一张票即可定论、何时必须等下一轮，并在票实际收到后用属于本次预约的见证判定原组合能否交付；同一实体量块始终是同一个未知长度。演练：`python3 -B examples/witness_plan_case.py`。

### 成品复核与交接

运行 `witness` 后在结果中打开「查看复核交接」。合格成品可通过复核后签发；不合格成品可退回且保留原判定。发布新修订或恢复旧修订都会换代，已经通过但未签发的旧复核不能补签。已签凭据可从同一运行的历史复核中下载。

旧版工作台数据库打开时会在事务中自动升级到 SQLite 结构 v2，不改写原始录入、历史运行或证据。升级后的数据库不再由旧版工作台打开；保留旧版时请使用数据库的独立副本。

兼容保留原 HTTP 服务和数据格式，以下是原服务说明。

---

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

### 组块实测见证核验

发布更新后的 `examples/workbench.json`，在结果区选择「组块实测见证核验」。验收命令：`python3 -B examples/workbench_check.py witness`。这项加工可选；老原料不含 `witness_readings` 时仍可使用原操作。
