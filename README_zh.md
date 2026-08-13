# steg-lab

一套面向 Kali Linux 的隐写分析知识库：理论带可证伪的验收判据，实战模块的检测器是
量出来的，不是描述出来的。

**版本 1.0.0。** 十七个模块覆盖全部载体类别——容器、空域、JPEG-DCT、调色板、音频、
文本、网络、视频与三种文件系统——八章理论各带一道通过的 gate、一条可执行的取证流水线，
以及一条对 Python 参考实现做差分测试的 Rust 分流侧线。

这里每一个解析器都对着一个独立实现做过交叉验证：pngcheck、djpeg、标准库 `wave` 模块、
tshark、ffmpeg、mtools、debugfs、ntfscat。每一个阈值都是在它所适用的那个载体上量出来的，
而当一项检查没有检验力时，它拒绝运行而不是产出一个数字。这个仓库做不到什么写在
[GAP_ANALYSIS_zh.md](GAP_ANALYSIS_zh.md) 里，包括它拒绝尝试的事情以及理由。
<!-- claim:labs=17 -->
<!-- claim:gates=8 -->

## 本仓库赖以成立的那条规则

智能合约审计有 `No PoC, no High`：严重度主张要么有可执行的 exploit 撑着，要么降级。
隐写分析需要同样形状的规则，但它的判定是统计性而非确定性的，所以撑腰的东西不一样：

> **无提取、无基线，不定性。**

具体地说，一条发现只有携带了在**同源**干净载体上实测的误报率，才能报到 E3 或以上。
`steganalysis.evidence.Finding.assert_reportable()` 是抛异常而不是发警告，因为警告
在赶工期时会被忽略。

## 证据阶梯

| 级别 | 含义 | 要求 |
|---|---|---|
| E0 | 无异常 | -- |
| E1 | 可疑，但正常处理链能解释 | 无 |
| E2 | 统计异常 | 已实测基线 |
| E3 | 确认存在隐写 | 基线 + 已识别嵌入域 |
| E4 | 载荷已提取（密文也算） | 载荷字节 |
| E5 | 密钥或口令已恢复 | 完整提取可复现 |

E1 的存在，是为了给分析员一个诚实的地方放「这看着不对，但我排除不了正常处理」。

## 目录结构

```
docs/theory/      T0-T7 chapters, each gated
docs/cases/       real-incident narratives
labs/NN_name/     one carrier family per lab: embed, detect, README
steganalysis/     shared library: parsers, evidence ladder, corpus
gates/            runnable acceptance criteria
rust/stegscan/    container triage at scale, zero dependencies
corpus/           seeded generation; no image bytes in the repository
scripts/          setup, verification, doc checks, differential test
tests/            pytest suite
```

## 快速开始

```bash
bash scripts/setup-kali.sh
bash scripts/verify-toolchain.sh
python3 corpus/generate.py
python3 -m pytest tests -q
python3 gates/g0_wardens.py
python3 gates/g1_parsers.py
```

或者用 make：

```bash
make setup verify corpus test gates
```

## P0 量出来的东西

| 结果 | 数值 |
|---|---|
| 被动看守，载荷误码率 | 0.0 |
| 主动看守对 LSB，JPEG q90 中位误码率 | 0.498 |
| 主动看守对 steghide，提取失败次数 | 12/12 |
| 恶意看守，伪造被接受次数 | 12/12 |
| PNG 解析器对 pngcheck，chunk 分歧 | 162 中 0 |
| JPEG 解析器对 djpeg，量化表分歧 | 100 中 0 |
| Rust 对 Python 差分，字段分歧 | 210 文件 x 9 字段中 0 |
| Rust 分流相对 Python 的加速 | 4.0x |
| 结构化多态检测器，误报 | 0/500 |
| 签名扫描检测器，误报 | 2/500 |
| F5 矩阵编码效率对理论值，最大误差 | 0.47% |
| F5 因收缩损失的嵌入效率 | 45.3% |
| Weighted Stego 对 LSB replacement 在 0.25 bpp 的 AUC | 1.000 |
| 同一批检测器对 LSB matching，最大偏离随机水平 | 0.086 |
| Weighted Stego 载荷估计平均绝对误差 | 0.031-0.044 |
| 同一检测器，基线来源匹配对失配，误报率 | 0% 对 25% |
| SPAM686 + 集成对 LSB matching 在 1.0 bpp 的 P_E | 0.140 |
| 同一任务上最好的结构检测器 P_E | 0.450 |
| 同一分类器在来源失配下的 P_E | 0.487（随机） |
| JPEG 编码器往返，系数分歧 | 0 |
| Jsteg 检测，载荷 200-1100 字节 | 10/10，误报 0/30 |
| Jsteg 载荷长度估计，真值 800 字节 | 估计 793 |
| STC 失真对率失真界（h=12） | +7.93% |
| HILL 改动密度，纹理 : 平坦（uniform 对照 0.98） | 1.84 |

以及在真实 BOSSbase 载体上——上面那些数字从这里开始不再是暂定的：

| BOSSbase 1.01 上的结果 | 数值 |
|---|---|
| Weighted Stego 对 LSB replacement 在 0.05 bpp 的 AUC（合成：0.594） | **0.882** |
| 卡方在干净载体上的平均 p 值（合成：0.944） | **0.129** |
| RS 与 WS 在各自 95% 真阳性阈值处的误报 | 各 0/200 |
| SPAM686 + 集成对 LSB matching 在 1.0 bpp 的 P_E | 0.125 |
| 跨相机位移后的 P_E（canon_eos_7d → nikon_d70） | 0.160 |
| 同一批图像仅做一次重采样后的 P_E | 0.500 |
| HILL+STC 对 LSB matching 在 0.4 bpp 的 P_E | **0.344 对 0.198** |
| STC 与率失真界的差距（h=12，带密钥嵌入路径） | **5.98%** |
| 校准攻击检测 F5，干净载体误报 | 0/24 |
| 盲测收官：30 次封存试验，干净载体过度断言 | **0** |
| 盲测收官：嵌入域命名正确 | 23/23 |
| Weighted Stego 对音频 LSB 的响应，8 位对 16 位载体 | **20.7x 对 1.1x** |
| 音频静音检查，两种位深下的误报 | 0/16 |
| 文本检测器在合法多语种语料上 | 0/8 误报 |
| 分散型文本对手：最长连续段 对 ASCII 字母间段数 | 1 对 48 |
| 网络：三条隐蔽信道的检出与提取 | 各 12/12，误报 0/12 |
| 时序信道：前两取值占比，背景对信道 | 0.03 对 >0.5 |
| pcap 解析器对 tshark 4.2.2 | 6,400 次字段比对零分歧 |
| 视频时序 LSB：干净峰值 对 载荷峰值 | 0.005 对 0.084 |
| 视频：MPEG-4 重编码后载荷与信号 | 双双被摧毁 |
| 渐进式 JPEG 系数对同图的基线编码 | 逐位相同 |
| FAT 文件 slack：全新格式化卷上的非零字节 | 0 |
| 被删文件残留 对 刻意放置的载荷 | 不可区分 |
| NTFS 驻留 ADS：读回逐字节精确 / 镜像中连续 | 是 / **否**（fixup） |
| Sample Pair Analysis 载荷估计，真值 0.20 / 0.40 | 0.208 / 0.391 |
| 盲测收官，覆盖全部九个载体域 | 34/40，**0 过度断言** |
| CNN 移除固定高通层的代价（BOSSbase 128px） | **P_E 0.163 → 0.493（随机）** |
| CNN 对 SPAM686 + 集成，同一划分（BOSSbase） | 0.257 对 0.170 |
| STC 差距对代价动态范围（其余全固定） | 60x 范围 533% → 7.5x 范围 **64%** |

多态那两行来自同一个模块，两条 LSB 行也是。两个落差都是证据阶梯存在的论据。

## 本仓库拒绝做的三件事

**不随包发布二进制载体。** 语料由种子生成、以 SHA-256 锁定，这让「同源」成为可校验
的属性，而不是一句主张。

**不写没跑过的命令。** `scripts/check-docs.py` 会校验文档里的 flag 确实存在、占位符
对 shell 安全、被引用的脚本真的在。这关掉的是一类在姊妹项目里复发过四次的 bug。

**不在没有基线的情况下下判定。** 见上。

## 文档

- [学习路径](LEARNING_PATH_zh.md) -- 按什么顺序读什么
- [理论层](docs/theory/README_zh.md) -- T0-T7 及其 gate
- [分析员检查清单](STEGANALYSIS_CHECKLIST_zh.md) -- 单页速查
- [威胁模型模板](THREAT_MODEL_TEMPLATE_zh.md)
- [上手指南](GETTING_STARTED_zh.md) -- 半小时，结束时有一条你自己藏进去、
  再自己找出来的载荷
- [工具实践](docs/TOOL_PRACTICE_zh.md) -- 每个工具的输出会在哪里被读错，
  是在给本仓库解析器做交叉验证时量出来的
- [资源](RESOURCES_zh.md) -- 工具、语料、文献
- 参考语料：先 `bash scripts/get-corpora.sh`，再
  `python3 scripts/register-corpus.py`
- [维护者手册](MAINTAINERS_zh.md) -- 如何接续工作
- [缺口分析](GAP_ANALYSIS_zh.md) -- 明知缺失的部分

---

[English version](README.md)
