# 资源

这些工具各自会怎样误导人，见[工具实践](docs/TOOL_PRACTICE_zh.md)；本节只说它们是干什么的。

## 按层划分的工具链

| 层 | 工具 | 安装方式 |
|---|---|---|
| 容器分流 | binwalk, foremost, bulk_extractor, file, xxd | apt |
| 结构校验 | pngcheck, djpeg, jpegtran, exiftool | apt |
| 图像隐写 | steghide, outguess, zsteg, stegsolve, openstego | apt + gem + jar |
| 口令恢复 | stegseek, stegcracker, john, hashcat | 源码 / apt |
| 机器学习隐写分析 | aletheia, StegExpose | pip / jar |
| 音频 | sox, audacity, sonic-visualiser, ffmpeg | apt |
| 网络 | tshark, zeek | apt |
| 通用 | ImageMagick, Python 科学栈 | apt + pip |

Gate G0 与 G1 明确依赖 `pngcheck`、`djpeg` 与 `steghide`。缺了它们，gate 会跳过而
不是失败，而理论章节也就失去了它们的证据。

## 本系列中的相关工作

- **stegseek-rs** -- stegseek 破解器的 Rust 重实现，覆盖 PRNG/selector 子系统、
  S2K KDF、AES-128-CBC 与 CVE-2021-27211 的种子利用。原计划在 P2 以 lab 17 的形式
  与它对接，最终没有建成——所以 **E5 是本仓库定义了却从未抵达的那一级**：steghide
  口令恢复正是 E4 到 E5 的典型跃迁，而在这里它只是一个指针。
- **sc-audit-lab** -- 本仓库借用其结构的智能合约审计实验室：理论带 gate、实战量化、
  中英 lockstep、文档检查器。

## 语料

| 语料 | 内容 | 用途 |
|---|---|---|
| BOSSbase 1.01 | 10,000 张灰度 512x512，七台相机 | 空域基线 |
| BOWS2 | 10,000 张灰度 512x512 | 载体来源失配实验 |
| ALASKA2 | 约 75,000 张彩色 JPEG，多档质量因子 | JPEG 域、贴近现实的混合场景 |

以引用方式获取，绝不入库：`bash scripts/get-corpora.sh`。

## 标准与框架

隐写分析没有 OWASP Top 10 的对应物，所以框架来自取证，而不是来自漏洞分类法：

- **NIST SP 800-86** -- 将取证技术整合进事件响应
- **ISO/IEC 27037 / 27042** -- 数字证据的识别与保全；分析与解释
- **SWGDE** -- 图像分析与真实性鉴定指南
- **Daubert** -- 可采信性标准，正是它让「你的错误率是多少」成为你会在宣誓下被问到的
  问题，也是证据阶梯要求实测基线的原因
- **MITRE ATT&CK** -- T1027.003（混淆文件：隐写）与 T1001.002（数据混淆：隐写式），
  作为威胁情报锚点

在把这些编号用于任何具证据效力的场合之前，请对照原始来源核实；本清单编于 v0.1.0-P0。

## 文献

- Fridrich，*Steganography in Digital Media: Principles, Algorithms and
  Applications*（2009）-- 本领域的标准参考书
- Simmons，"The Prisoners' Problem and the Subliminal Channel"（1984）
- Cachin，"An Information-Theoretic Model for Steganography"（1998, 2004）
- Hopper、Langford、von Ahn，"Provably Secure Steganography"（2002）
- Ker 等，"Moving Steganography and Steganalysis from the Laboratory into the
  Real World"（2013）-- 讲实验室结果为何无法迁移的那篇，引用任何 P_E 数字之前必读

## 格式规范

- PNG：ISO/IEC 15948
- JPEG：ITU-T T.81
- ZIP：PKWARE APPNOTE.TXT

请读原文。A 组的每一处藏身之所，都是规范所允许之事的后果，而规范本身写得明明白白。

---

[English version](RESOURCES.md)
