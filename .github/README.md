<!-- twins:single-language GitHub 访客落地页；英文见 ../README.md，不做逐句对照 -->

<div align="center">

# steg-lab

**面向 Kali Linux 的隐写分析知识库**

理论带可证伪的验收判据，检测器的阈值是量出来的，不是描述出来的。

[![ci](https://github.com/adomore/steg-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/adomore/steg-lab/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-1.0.0-2C558F)
![labs](https://img.shields.io/badge/实战模块-17-2C558F)
![gates](https://img.shields.io/badge/验收%20gate-8-2C558F)
![docs](https://img.shields.io/badge/文档-中英对照-2C558F)

[English](../README.md) · [学习路径](../LEARNING_PATH_zh.md) · [上手指南](../GETTING_STARTED_zh.md) · [缺口分析](../GAP_ANALYSIS_zh.md)

</div>

<!-- claim:labs=17 -->
<!-- claim:gates=8 -->
<!-- claim:theory_chapters=8 -->

---

## 这个仓库赖以成立的那条规则

智能合约审计有 `No PoC, no High`：严重度主张要么有可执行的 exploit 撑着，要么降级。隐写分析需要同样形状的规则，但它的判定是统计性而非确定性的，所以撑腰的东西不一样：

> ### 无提取、无基线，不定性。

一条发现只有携带了在**同源**干净载体上实测的误报率，才能报到 E3 或以上。`Finding.assert_reportable()` 是抛异常而不是发警告 —— 因为警告在赶工期时会被忽略。

## 证据阶梯

| 级别 | 含义 | 要求 |
|:---:|---|---|
| `E0` | 无异常 | — |
| `E1` | 可疑，但正常处理链能解释 | 无 |
| `E2` | 统计异常 | 已实测基线 |
| `E3` | 确认存在隐写 | 基线 + 已识别嵌入域 |
| `E4` | 载荷已提取（密文也算） | 载荷字节 |
| `E5` | 密钥或口令已恢复 | 完整提取可复现 |

E1 的存在，是为了给分析员一个诚实的地方放「这看着不对，但我排除不了正常处理」。

## 快速开始

```bash
bash scripts/setup-kali.sh
bash scripts/verify-toolchain.sh
python3 corpus/generate.py
python3 -m pytest tests -q
python3 gates/g0_wardens.py
```

或者用 make：

```bash
make setup verify corpus test gates
```

## 覆盖范围

十七个实战模块横跨九个载体域，八章理论各带一道**可执行**的 gate。

| 组 | 模块 | 载体 / 域 |
|:---:|---|---|
| **A** | `01`–`06` | 容器结构：尾部数据、多态、元数据、PNG 块、ZIP 目录、JPEG 段 |
| **B** | `07`–`09` | 空域：LSB 替换、LSB 匹配、SPAM/SRM 特征加集成 |
| **C** | `10` `13` `14` | 调色板与 JPEG-DCT：EzStego、Jsteg、F5 校准攻击 |
| **D** | `18` `20` | 音频与文本：WAV LSB 与静音、零宽字符与尾部空白 |
| **E** | `21`–`23` | 网络、视频、文件系统：隐蔽信道、帧间时序、FAT/ext4/NTFS |

每一个解析器都对着一个独立实现做过交叉验证 —— pngcheck、djpeg、标准库 `wave`、tshark、ffmpeg、mtools、debugfs、ntfscat。**当一项检查没有检验力时，它拒绝运行而不是产出一个数字。**

## 几个量出来的结果

| 结果 | 数值 |
|---|:---:|
| Weighted Stego 对 LSB replacement，0.05 bpp（BOSSbase） | AUC **0.882** |
| SPAM686 + 集成对 LSB matching，1.0 bpp | P_E **0.125** |
| 同一批图像仅做一次重采样后 | P_E **0.500** |
| CNN 移除固定高通层的代价 | P_E 0.163 → **0.493** |
| 盲测收官，覆盖全部九个载体域 | 34/40，**0 过度断言** |
| Rust 对 Python 差分，210 文件 × 9 字段 | **0 分歧** |

两条 LSB 的落差不是缺陷，是证据阶梯存在的论据 —— **一个开始能检出 LSB matching 的结构检测器是坏了，不是变好了。**

## 本仓库拒绝做的三件事

- **不随包发布二进制载体。** 语料由种子生成、以 SHA-256 锁定，让「同源」成为可校验的属性而不是一句主张。
- **不写没跑过的命令。** `scripts/check-docs.py` 校验文档里的 flag 确实存在、占位符对 shell 安全、被引用的脚本真的在。
- **不在没有基线的情况下下判定。** 见上。

## 文档

| | |
|---|---|
| [README_zh.md](../README_zh.md) | 完整说明与全部实测数据表 |
| [LEARNING_PATH_zh.md](../LEARNING_PATH_zh.md) | 按什么顺序读什么 |
| [GETTING_STARTED_zh.md](../GETTING_STARTED_zh.md) | 半小时，结束时有一条你自己藏进去、再自己找出来的载荷 |
| [docs/theory/README_zh.md](../docs/theory/README_zh.md) | 理论层 T0–T7 及其 gate |
| [STEGANALYSIS_CHECKLIST_zh.md](../STEGANALYSIS_CHECKLIST_zh.md) | 分析员单页速查 |
| [docs/TOOL_PRACTICE_zh.md](../docs/TOOL_PRACTICE_zh.md) | 每个工具的输出会在哪里被读错 |
| [GAP_ANALYSIS_zh.md](../GAP_ANALYSIS_zh.md) | 明知缺失的部分，以及花掉真实调试时间的发现 |
| [MAINTAINERS_zh.md](../MAINTAINERS_zh.md) | 如何接续工作 |
| [RESOURCES_zh.md](../RESOURCES_zh.md) | 工具、语料、文献 |

---

<div align="center">

英文文档与中文严格对照，由 `scripts/check-docs.py` 强制。

**[English version →](../README.md)**

</div>
