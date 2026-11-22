# 计量决策说明：两个候选投产日的校正量与半径，以及证书缺口的处理

范围：虚拟测量工位。本说明只使用仓库现有 `/stackfit/certificate-status` 与 `/stackfit/stack-interval` 入口，数据来自 `analysis/scenario.json`，不涉及真实设备校准或认证。

## 1. 计量原则

- 长度单位是整数纳米。证书有效区间**左闭右开**，即 `from <= 日期 < until`。
- 某日期上若有**多于一张**证书覆盖同一块，该块在该日期不可用，原因记为 `overlap`；不得挑一张"看起来对"的证书。
- 某日期上若无证书覆盖，原因记为 `no_valid_certificate`；**不得用名义长度代替**。
- 每块在某日期只有两种输出：可用的（校正值、半径、证书号、绝对边界）或不可用的（原因）。没有中间态。
- 组合的绝对半径按块**相加**，不假设独立误差。

## 2. 两个日期的逐块结果

数值全部来自 `/stackfit/certificate-status`；`corr` 为校正值，`r` 为绝对不确定半径；不可用块不给任何数值。

| 块 | D1 2026-11-15 | D2 2026-12-15 |
| --- | --- | --- |
| C | corr +1, r 3, `c-c` | corr +1, r 3, `c-c` |
| D | corr 0, r 1, `c-d` | **不可用** `no_valid_certificate`（证书到 2026-12-01 右开结束） |
| F | **不可用** `no_valid_certificate`（证书 2026-12-01 起效） | corr −1, r 2, `c-f` |
| J | corr 0, r 1, `c-j` | **不可用** `no_valid_certificate`（证书到 2026-12-01 右开结束） |
| H | 不可用 `no_valid_certificate` | 不可用 `no_valid_certificate` |
| I | **不可用** `overlap` | **不可用** `overlap` |
| S-A | corr +1, r 2, `q-sa` | corr +1, r 2, `q-sa` |
| S-B | corr 0, r 1, `q-sb` | corr 0, r 1, `q-sb` |
| S-C | corr 0, r 20, `q-sc` | corr 0, r 20, `q-sc` |
| S-D | corr 0, r 2, `q-sd` | corr 0, r 2, `q-sd` |

要点：
- **D、J** 的证书 `until=2026-12-01`，因右开在 D2（2026-12-15）无效；这不是"过期一两天"，而是区间定义。
- **F** 从 2026-12-01 起效，D1 完全无证书。
- **H** 证书到 2026-11-01，两个候选日都已失效。
- **I** 的两张证书在两张候选日都同时覆盖，稳定判为 `overlap`，任何日期都不给值。
- **S-C** 半径 ±20 本身已超过公差 ±12；即使校正为 0，任何组合的相加半径也 ≥ 20，裕量不可能 ≥ 0，本数据里最好的组合也仍是 `partial`（裕量 −13）。

## 3. 证书缺口与重叠的反例（不得名义化）

以下三个探针都返回 HTTP 200 + `state=unresolved`，而不是给出数值（见 `decision_matrix.json` 的 `counterexamples`）：

| 探针 | 日期 | 组合 | 结果 |
| --- | --- | --- | --- |
| 重叠 | D1 | `[S-A, I, J]` | `unresolved`，`I: overlap` |
| 缺口 | D1 | `[S-A, F, C]` | `unresolved`，`F: no_valid_certificate` |
| 过期 | D2 | `[S-A, D, C]` | `unresolved`，`D: no_valid_certificate` |

若把 I 的名义 200 000、F 的名义 300 000、D 的名义 300 000 代入，都会得到"看起来合规"的假结果。入口的 `unresolved` 就是对这种代入的拒收。

复现：

```sh
python3 -B -m gauge.example /stackfit/certificate-status \
  --input analysis/out/inputs/base-S-A-D1-certificate-status.json
python3 -B -m gauge.example /stackfit/stack-interval \
  --input analysis/out/inputs/base-S-B-D1-stack-interval.json
```

## 4. 每日可用的校正量与半径汇总（供组装前核对）

组装日确认后，计量只需看该日期这一列，并与当天的在库证书核对：

- D1 可用：C(+1,3)、D(0,1)、J(0,1)、S-A(+1,2)、S-B(0,1)、S-C(0,20)、S-D(0,2)。
- D2 可用：C(+1,3)、F(−1,2)、S-A(+1,2)、S-B(0,1)、S-C(0,20)、S-D(0,2)。

组合边界 = Σ(名义 + 校正) ± Σ半径。计量不对"名义长度"背书，只对证书给出的校正/半径背书。

## 5. 与采购结论的接口

- 采购的"可先下单"必须由计量的逐日可用表支撑：某报价在其所有候选日都可算出合规组合。
- 采购若引用固定组合，计量需确认该组合在两个日期的每块都可用，且边界一致（本数据仅 S-D 的 `[C, S-D]`）。
- 采购若引用"迟定装配"，计量只确认"每块在其各自日期可用"，不承诺跨日期同组合。

## 6. 变更对照（只改一张证书的生效日）

变体只把 S-A 的证书 `from` 从 2026-10-01 改为 2026-12-01：

- D1：S-A 变为 `no_valid_certificate`，该日不可用。
- D2：S-A 仍是 corr +1, r 2，可用。
- 其余所有块、两个日期的数值与类别不变（S-D 的固定组合仍在）。

也就是说，同一张报价单的表在 D1 由"可用"变为"不可用"，但 D2 不受影响；这正是"单块证书生效日"这一变量能造成的全部差异。

## 7. 复查

1. `analysis/out/decision_matrix.json` 的 `results.<base|variant>.<quote>.dates.<D1|D2>.status` 与 §2 表逐格一致。
2. `counterexamples[*].state` 全为 `unresolved`。
3. `verification.ok=true` 且 `self_check.changed_fields=["from"]`。
