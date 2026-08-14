# RAG 评测错误用例分析

> 数据来源：`backend/eval/report_manual.json`（人工评测集 40 题，schema_version 2）。
> 分析方法：`backend/eval/diag_retrieval.py` 对每个错误用例输出 gold 片段全文 + 纯向量 / 混合(无重排) / 混合(加重排) 三路 top-5。

## 1. 错误分布

40 题（positive 32 / negative 8）中，positive 侧错误 10 例：

| 错误分类 | 数量 | 占比 | 用例 |
|---|---|---|---|
| retrieval_miss（gold 未进 top-5） | 8 | 25.0% | Q11, Q14, Q16, Q17, Q18, Q22, Q24, Q30 |
| unfaithful（答案未被片段支撑） | 2 | 6.2% | Q2, Q6 |
| low_correctness（corr ≤ 2） | 0 | 0% | — |
| ok | 22 | 68.8% | — |

负样本侧：reject_rate 1.0，hallucination_rate 0.0，全部正确拒绝。

---

## 2. 根因：分块器在句子/单词中间切块

**核心结论：8 例 retrieval_miss + 2 例 unfaithful 的根因高度集中——`chunker` 按固定长度硬切，不感知句子边界。** 结果 gold 片段以句子中段 / 单词中段开头，或吞进了表格/图表题注/页脚/标题栏等版面噪声。

### 2.1 片段以句子中段开头（稀释语义）

| 用例 | gold 块开头 | 说明 |
|---|---|---|
| Q11 (gt=11) | `s [29], WebQuestions [3] and CuratedTrec [2] and strongly outperform...` | 句子被切断，「TriviaQA/FEVER 表现」的完整语义只在片段中部 |
| Q14 (gt=9) | `sis (assuming the same document is responsible for all tokens)...` | 从单词 "hypothe-**sis**" 中段开始 |
| Q16 (gt=64) | `neration models with access to parametric and non-parametric memory...` | 从 "ge-**neration**" 中段开始 |
| Q24 (gt=17) | `domain QA is based on a sequence-to-sequence network...` | 上一句被切走一半 |
| Q30 (gt=24) | `swers in uppercase are normalized by converting all let- ters...` | 从 "An-**swer**s" 中段开始 |
| Q2 (gt=20) | `when generating from BART, we simply concatenate them...` | 上一句的「参数如何作为记忆使用」上下文在片段之外 |

这类片段的开头是半个词/半句话，嵌入向量被无意义 token 稀释，语义锚点弱 → 检索排名靠后或漏检。

### 2.2 版面噪声混入正文块（表/图注/标题/页脚）

| 用例 | 污染源 | 说明 |
|---|---|---|
| Q18 (gt=4) | 图 1 题注 | gold 块是「Where was Alan Turing born? Maida Vale, London Figure 1...」的**图注区域**，视觉布局文本主导嵌入；真实方法描述在同段相邻块 chunk 6（已被检索到） |
| Q22 (gt=15) | 表 1 数字 | gold 块以 `1.2 - - Fusion-in-Decoder (base) 48.2 65.0... Table 1:...` 表格数字开头，答案「BM25 和 DPR」排在表格之后 |
| Q24 (gt=17) | 页脚 URL | gold 块结尾带 `1lucene.apache.org 2spacy.io 3github.com/facebookresear...` 脚注链接 |
| Q17 (gt=0) | 标题 + 作者栏 | gold 块是论文标题 + 作者 + Abstract 开头；「核心方法/成果」结论实际上在 chunk 0/1 边界被切开，chunk 1 已被检索到 |

### 2.3 结果：gold 与「实际可答题片段」错位

多个案例中，**真正含答案的相邻块其实被检索到了**（如 Q17 的 chunk 1、Q18 的 chunk 6），只是标注的 gold 块恰好是切在边界上的碎片/版面块。说明：
- 检索侧"够用"，但**硬切分块 + 版面块污染**让 gold 标注变脆；
- 这也解释了为何这些题 generation 得分不低（Q16 corr=5、Q17 corr=5、Q18 corr=5），只是 hit@k 记错。

---

## 3. 一个评测口径问题：manual 评测的 hybrid 没开 rerank

`evaluate.py:225` 的 hybrid 路径用 `rerank=False`，但**生产检索与 `run_multi_eval.py` 都默认 `rerank=True`**（`hybrid_search` 默认值）。

用 `diag_retrieval.py` 对 8 个 miss 用例重跑 rerank 路径后，**3 例被重排找回**：

| 用例 | 纯向量 | 混合(无重排) | 混合(加重排) |
|---|---|---|---|
| Q16 (gt=64) | miss | miss | **gold@2** |
| Q22 (gt=15) | miss | miss | **gold@4** |
| Q30 (gt=24) | miss | miss | **gold@1** |
| Q6 (gt=19) | gold@5 | gold@5 | **gold@4** |

即 manual 评测的 hybrid hit_rate（75.0%）**低估了生产路径**（生产带 cross-encoder 重排）。`run_multi_eval` 的 hybrid 数字已含 rerank，两套脚本口径不一致。

---

## 4. unfaithful 两例复盘

- **Q2**（gold@1，三路全命中）：检索没问题。gold 块从句子中段开始（`when generating from BART...`），丢了「参数如何作为参数化记忆使用」的上文；模型据此回答为「片段未详细说明参数如何作为记忆使用」，被 judge 判 unfaithful（corr=3.0 中等）。属**分块上下文缺失 + judge 偏严**，非检索漏检。
- **Q6**（gold@4-5，边缘命中）：gold 落在 top-4/5，而**生成答案只用了 top-3 上下文**（`evaluate.py` 的 `_answer` 取 `chunks[:3]`），gold 没进上下文 → 答案基于无 gold 的 top-3 作答 → judge 判 unfaithful（corr=2.0）。属**边缘召回 + 答案上下文窗口过窄**。

---

## 5. 改进建议（按性价比排序）

1. **分块器感知句子/段落边界**（最重要）：切块时在句子边界对齐，或加 overlap，杜绝「半个单词/半句话开头」。可一举改善上述 8/10 例。
2. **版面噪声过滤**：复用/扩展参考文献过滤的思路，新增「表格/图注/页脚 URL/标题作者栏」块的识别与剔除（或低权重）。例：含 `lucene.apache.org` 页脚、`Figure \d+:` 图注、纯数字表格的块。
3. **评测口径对齐**：`evaluate.py` 的 hybrid 改成 `rerank=True` 与生产/`run_multi_eval` 一致（会小幅提升 hybrid hit_rate，且更真实）。代价是每问多一次 cross-encoder 重排。
4. **生成上下文放宽**：`_answer`/`_judge` 用 top-5 而非 top-3，或对边缘命中的 gold（rank 4-5）做一次「邻近块合并」，降低 unfaithful。

---

## 6. 工程价值与方法论

- 这 10 例全部可归因于**工程实现细节**（分块边界、版面块、评测口径），而非"RAG 无用"；
- 证明有**完整错误归因方法论**：`report_manual.json` 错误分类 → `diag_retrieval.py` 逐例定位 → 根因归类 → 修复方向；
- 评测本身**暴露了自己的口径不一致**（manual 无 rerank vs 生产有 rerank），是「评测 → 生产 反馈闭环」又一个实例，与已有的参考文献过滤反哺同源。
