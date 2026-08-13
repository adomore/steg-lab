# 上手指南

半小时，结束时你会有一条自己藏进去、再自己找出来的载荷，以及一个数字——它解释了这个仓库
为什么被建成现在这样。

这不是阅读顺序（那是[学习路径](LEARNING_PATH_zh.md)），也不是办案顺序（那是
[检查清单](STEGANALYSIS_CHECKLIST_zh.md)）。这是第一天。

## 安装

```bash
bash scripts/setup-kali.sh
python3 scripts/verify-toolchain.sh 2>/dev/null || bash scripts/verify-toolchain.sh
```

不是 Kali 的话，按 `requirements.txt` 装 Python 依赖，再用你的包管理器装
`pngcheck`、`libjpeg-progs`、`dosfstools`、`mtools`。

然后弄清楚**什么会静默地不运行**：

```bash
python3 scripts/check-crossval.py
```

这里每一个手写解析器都对着一个独立工具做校验，而每一项这样的测试在工具缺失时都会干净地跳过。
**一次被跳过的交叉验证，与一次通过的交叉验证报出同样的绿色**，所以这个脚本会为每一项打印
RUNS 或 SKIP，并在有任何一项会跳过时以非零码退出。

## 在信任这个仓库之前先验证它

```bash
python3 -m pytest tests -q
python3 scripts/check-docs.py
python3 gates/g0_wardens.py
```

那些 gate 是理论章节的验收判据。**一章不是「写得好看」就算完成，是它的 gate 通过才算完成。**

## 亲手藏一样东西，再把它找出来

五条命令，而第四条才是重点。

```python
from steganalysis import corpus
from labs.common import load_lab

cover = corpus.render(corpus.CoverSpec("cover.png", 1, 128, 128,
                                       "photo_like", "png"))
lab = load_lab("01_trailing_data")
stego = lab.embed(cover, b"MEET AT NOON")

report = lab.detect(stego, "stego.png", baseline=None)
print(report.verdict)                     # E1
print(report.findings[0].payload)         # None
```

载荷是 PNG 的 `IEND` 标记之后的 12 个字节。检测器找到了它、说了出来，然后
**拒绝把它交出来**。这就是这个仓库赖以建立的那条规则，而且它是**用代码强制的**，不是用散文建议的。

现在量一个基线，再跑一次：

```python
from steganalysis.evidence import FalsePositiveBaseline

clean = [corpus.render(corpus.CoverSpec(f"c{i}.png", 100 + i, 128, 128,
                                        "photo_like", "png"))
         for i in range(12)]
false_positives = sum(1 for c in clean
                      if lab.detect(c, "c", baseline=None).verdict >= 1)
# 实测：12 张里 0 个

baseline = FalsePositiveBaseline("trailing_data", 12, false_positives, 0.0,
                                 "12 same-source clean PNGs")
report = lab.detect(stego, "stego.png", baseline=baseline)
print(report.verdict)                     # E4
print(report.findings[0].payload)         # b'MEET AT NOON'
```

**从 E1 到 E4，而且载荷出来了。** 载体本身没有任何变化。变的是：这个论断现在附带一个在
**同源载体**上实测的误报率——那正是「怀疑」与「发现」之间的差别。

## 对一个未知文件跑完整流水线

```python
from steganalysis import pipeline

result = pipeline.analyse(open("stego.png", "rb").read(), "stego.png")
print(pipeline.render(result))
```

流水线按容器类型派发，先跑结构模块再跑统计模块，并且**拒绝**把在一种载体上校准的阈值套到
另一种载体上。对干净载体它报 E0，别的什么也不说。

## 接下来去哪

| 你想要 | 读 |
|---|---|
| 学习的先后顺序 | [LEARNING_PATH_zh.md](LEARNING_PATH_zh.md) |
| 拿到真实检材该怎么办 | [STEGANALYSIS_CHECKLIST_zh.md](STEGANALYSIS_CHECKLIST_zh.md) |
| 每个工具会怎样误导你 | [docs/TOOL_PRACTICE_zh.md](docs/TOOL_PRACTICE_zh.md) |
| 理论，每章带一道 gate | [docs/theory/](docs/theory/README_zh.md) |
| 这个仓库仍然做不到什么 | [GAP_ANALYSIS_zh.md](GAP_ANALYSIS_zh.md) |

## 三个值得从这里带走的习惯

**先量基线，再下判定。** 不是先下判定、再回头找基线来支撑它。这个仓库里每一个阈值都是
「它被量出来的那个载体」的属性，而跨来源引用阈值是「自信地搞错」最常见的方式。

**一项没有检验力的检查应当拒绝运行，而不是产出一个数字。** Lab 22 在传感器噪声已经把低位
随机化的视频上拒绝运行；Lab 21 把 IP-ID 信道封顶在 E1，因为一个会随机化的网络栈与载荷不可
区分。**拒绝也是一种结果。**

**记录你没有检验什么。** 覆盖缺失不等于风险缺失，而一份不说自己跳过了什么的报告，等于在
暗示它什么都没跳过。

---

[English version](GETTING_STARTED.md)
