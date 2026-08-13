# 理论层

八章，T0 到 T7。每一章都以一道 **gate** 收尾：一条可证伪的验收判据，以 `gates/`
下可运行的脚本形式实现。一章不是写得好看就算完成，而是它的 gate 在本机通过才算完成。

Gate 里可以包含必须**失败**的判据。T4 的 gate 要求 RS 与 Sample Pair Analysis 在
LSB matching 面前崩溃，因为一门只演示成功的课程，会把分析员训练成预期成功。

## 状态

| 章节 | 主题 | Gate | 状态 |
|---|---|---|---|
| T0 | 问题定义与威胁模型 | G0 | 通过 |
| T1 | 载体与嵌入域 | G1 | 通过 |
| T2 | 经典嵌入算法 | G2 | 通过 |
| T3 | 自适应嵌入与失真最小化 | G3 | 通过 |
| T4 | 统计隐写分析 | G4 | 通过 |
| T5 | 特征集与集成分类 | G5 | 通过 |
| T6 | 深度学习隐写分析 | G6 | 通过 |
| T7 | 取证工作流与决策 | G7 | 通过 |

## 阅读顺序

T0 与 T1 是其余一切的前置。之后 T2 与 T4 天然成对（一种攻击及其检测），T3 与 T5
亦然。T6 依赖 T5。T7 依赖全部，且它的 gate 就是收官之作。

## 章节

- [T0 -- 问题定义与威胁模型](T0_threat_model_zh.md)
- [T1 -- 载体与嵌入域](T1_carriers_and_domains_zh.md)
- [T2 -- 经典嵌入算法](T2_classical_algorithms_zh.md)
- [T3 -- 自适应嵌入与失真最小化](T3_adaptive_embedding_zh.md)
- [T4 -- 统计隐写分析](T4_statistical_steganalysis_zh.md)
- [T5 -- 特征集与集成分类](T5_feature_sets_zh.md)
- [T6 -- 深度学习隐写分析](T6_deep_learning_zh.md)
- [T7 -- 取证工作流与决策](T7_forensic_workflow_zh.md)

---

[English version](README.md)
