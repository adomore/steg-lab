# 维护者手册

如何在不重新推导约定的前提下接续工作。

## 当前状态

版本 `1.0.0`。十七个模块、八章理论、八道 gate。
<!-- claim:labs=17 -->
<!-- claim:theory_chapters=8 -->

## 绿线

下面全部通过，才允许交付任何东西。

```bash
python3 -m pytest tests -q
python3 gates/g0_wardens.py
python3 gates/g1_parsers.py
python3 gates/g2_classical.py
python3 gates/g3_adaptive.py
python3 gates/g4_statistical.py
python3 gates/g5_feature_sets.py
python3 gates/g6_deep_learning.py --n 160 --epochs 18
python3 gates/g7_capstone.py

# 需要真实机器的检查（G-8、G-11、G-18、G-21）：
python3 scripts/analyst-checks.py

# 本机会静默跳过哪些交叉验证？
python3 scripts/check-crossval.py
python3 scripts/verify-jpeg-encoder.py
python3 scripts/check-docs.py   # EN/ZH structural lockstep included
python3 scripts/difftest.py --n 200
python3 corpus/generate.py --verify
bash scripts/verify-toolchain.sh
```

Rust 侧：

```bash
cd rust/stegscan && cargo test --offline -q
```

## 约定

**模块解剖。** `labs/NN_name/lab.py` 暴露 `NAME`、`DOMAIN`、`ALGORITHM`、
`embed(...)`、`detect(data, name, baseline=None)`。`detect` 必须接受
`baseline=None`，且在该情形下把发现压到 E1。目录名以数字开头，所以模块通过
`labs.common.load_lab` 按路径加载，而不是 import。

**每个检测器都要两个测试。** 一个测它在自己的隐写样本上会响，一个测它在 100 张同源
干净载体上保持沉默。只有前一个测试的检测器，是一个对什么都说「是」的检测器。

**基线是按检测器算的，不是按模块。** `measure_baseline` 按检测器名过滤。把一份报告里
的所有发现一起计数，会把弱启发式与强检测器混为一谈，产出一个哪个都不描述的数字。

**基线必须来源匹配。** 传 `kinds=`，让干净集与载体来自同一图像族。跳过这一步会把
Lab 07 的误报率从 0% 推到 25%——这就是载体来源失配，而且效应一点都不细微。

**未通过验证的检测器不进 `DETECTORS`。** 模块里有两个，改名加 `_UNVALIDATED` 后缀并
附文档。一个列着没人验证过的估计量的注册表，正是未经验证的数字混进报告的途径。

**中英 lockstep 从第一天起。** 每个 `.md` 都有 `_zh` 兄弟，标题结构完全一致。散文翻译，
代码、命令、flag、标识符与工具名不翻译。`check-docs.py` 强制这三条。

**Gate 就是验收判据。** 一章理论是它的 gate 通过才算完成，不是写得好看就算完成。
Gate 里可以包含必须**失败**的判据——G4 要求 RS 与 SPA 在 LSB matching 面前崩溃。

**仓库里不放二进制。** 语料由种子生成、以 SHA-256 锁定。

## 新增模块 NN

1. `mkdir labs/NN_name`，按上述接口写 `lab.py`。
2. 在 `labs/common.py` 的 `LAB_DIRS` 中加入 `"NN_name"`。
3. 写 `README.md` 与 `README_zh.md`，顶部放摘要表，含实测误报率。
4. 在 `tests/test_labs_a.py` 中加测试：检出、载荷复原、零误报。
5. 在 `STEGANALYSIS_CHECKLIST.md` 与 `_zh` 中各加一行清单。
6. 如果该模块改变了 Rust 扫描器所见，扩充 `scripts/difftest.py` 的异常样本集。
7. 跑绿线。

## 环境注意事项

- **PEP 668。** Kali 2024.1+ 与 Debian 12+ 会拒绝裸的 `pip3 install --user`。在
  `set -e` 下这会杀掉整个安装脚本，姊妹项目的 setup 脚本正是这么死的。
  `setup-kali.sh` 采用降级链：虚拟环境，其次 `--break-system-packages`，最后是带
  说明的显式跳过。
- **Gate 依赖。** G1 需要 `pngcheck` 与 `djpeg`（来自 `libjpeg-progs`）；G0 的判据
  B2 需要 `steghide`。三者缺失时是跳过而非失败，这让 CI 在精简镜像上保持诚实，但也
  意味着理论章节失去了证据支撑。
- **参考语料**放在仓库之外。把压缩包放到 `corpus/reference/`，跑
  `scripts/register-corpus.py`，然后给 G4 或 G5 传 `--corpus real`。loader 直接读取
  zip 成员，所以 1.6 GB 的包留着别解压，省下 2.6 GB。
- **rustfmt** 已安装、crate 已格式化，因此 `cargo fmt --check` 的 CI 步骤是硬失败，
  不是 `continue-on-error`。缺口 G-5 已关闭：未提交的重新格式化现在会让构建失败，
  而不是发一条警告。
- **Rust 仅 edition 2021**，与 apt 打包的工具链一致。

## 路线图

**P1 -- 已完成。** T2 与 T4；从零实现 LSB-R、LSB-M、Jsteg、F5；卡方、RS、WS 检测器；
模块 07 与 08；gate G2 与 G4。两个检测器写完后因未通过验证而未发布（缺口 G-11、
G-12），并且「合成语料不足以支撑统计工作」这一点是被量出来的，不是假定的。

**P2** -- T3 与 T5；STC 与自适应代价；SPAM/SRM 加集成分类；C 组 JPEG 域模块，复用
`decode_scan` 的系数输出；lab 17 对接 stegseek-rs。

**P3** -- T6 与 T7；D 组与 E 组；盲测收官 gate G7；有真实卷之后补文件系统 slack。

---

[English version](MAINTAINERS.md)
