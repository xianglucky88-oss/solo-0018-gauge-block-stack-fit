# 量块组合公差工作台

原生 HTML、CSS 和 JavaScript 工作台，业务计算由 Python 完成，使用本机 SQLite 持久化。无需安装前端依赖。仅用于本地合成样本，不对公网开放。

```sh
python3 -B -m workbench
```

浏览器打开命令输出的地址（默认 `http://127.0.0.1:8818`）。工作台支持样例与文件导入、发布历史、指定版本加工、对比、复算和证据导出。可用 `--port`、`--db` 指定本机端口和数据库文件。

新增领域加工：跨日组合复验、固定组合证书账、证书有效期分段。流程验收：`python3 -B examples/workbench_check.py`。

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
