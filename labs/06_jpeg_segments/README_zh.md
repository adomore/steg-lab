# Lab 06 -- JPEG 段空间，以及字节记账失效的地方

| | |
|---|---|
| 嵌入域 | container |
| 算法族 | comment-segment / rogue-appn / post-scan-padding |
| 检测器 | `jpeg_comment_segment`、`jpeg_rogue_appn`、`jpeg_scan_surplus`、`jpeg_byte_accounting` |
| 实测误报率 | 同源干净载体 0/100 |
| 证据上限 | E4 |

## 三个变体

**(a) COM 段。** 有文档记载的注释槽位，所有解码器都跳过。

**(b) 异常 APPn。** 出现在主流编码器不会使用的槽位上的标记段。真实编码器只用
`APP0`（JFIF）、`APP1`（EXIF/XMP）、`APP2`（ICC）、`APP13`（Photoshop IRB）和
`APP14`（Adobe）。其余都值得看一眼——尤其是当它带着一个看起来很像样的厂商签名时，
那正是内行的嵌入者会放进去的东西。

**(c) 扫描后填充。** 熵编码扫描结束与 `EOI` 之间的字节。

## 纯结构分析失效的地方

字节记账——每个字节要么属于某个段、要么属于扫描、要么就是一条发现——能关掉 (a)
和 (b)。它**关不掉** (c)，而搞清楚这一点是做这个模块最有价值的收获。

扫描没有声明长度，它到「下一个标记开始处」为止。填进不含 `0xFF` 的字节，扫描走查
会直接把它们吞掉，因为从外面看它们与压缩数据无法区分。这个检测器的第一版报告
「什么也没有」，而且它是对的。

要关掉 (c)，必须解码熵编码流，问最后一个 MCU 究竟在哪结束。这正是
`steganalysis.jpeg.decode_scan` 做的事：一个 baseline-sequential 的 Huffman 解码器，
输出 `consumed_end` 与 `physical_end` 的对比。在干净载体上，surplus 恰好为零。

这份代价值回两次票价——同一个解码器顺带给出了 C 组 JPEG 域模块需要的 DCT 系数。

## 扫描走查陷阱

靠搜索 `0xFFD9` 找 JPEG 的结尾是错的：压缩数据里会碰巧出现这个字节对。在扫描内部，
字面量 `0xFF` 以 `0xFF 0x00` 存储，只有第二字节非零且非 `RSTn` 才终止扫描。测试
断言了朴素搜索在样本上会落在扫描**内部**，所以这条理由是量出来的，不是讲出来的。

## 复现

```bash
python3 -m pytest tests/test_labs_a.py -q
```

## 它教什么

结构分析有一条下限。当一种格式拒绝声明长度时，你必须解码才能找到边界。这也正是
把它放在 A 组最后一个模块的原因。

---

[English version](README.md)
