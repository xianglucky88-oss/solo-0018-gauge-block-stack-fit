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
python3 -B -m gauge.example /stackfit/reuse-decision --input examples/reuse-decision.json
```

参见 [领域规则与接口](PROJECT_SPEC.md)。`examples/demo.json` 为完整合成输入；`examples/reuse-decision.json` 演示改动目标后判定上一张推荐单能否沿用；其他示例用于观察拒收或待核。当前不假设联网、数据库或已有用户数据。

## 测试

复用资格的合同测试由可替换适配器（进程内与本机 HTTP 两个实现）驱动，覆盖继续沿用、必须重搜、旧卡证书不可用三条路径，并以真实新请求作为验收对照：

```sh
python3 -B -m unittest discover -s tests -t .
```
