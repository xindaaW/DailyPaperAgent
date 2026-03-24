# Research Orchestrator Skill

## Purpose
用于控制论文雷达主 Agent 的自主执行：搜索、比较、综合、迭代、收敛并生成最终报告。

## Use this skill when
- 任务目标是生成一份“可读、可决策”的每日论文报告。
- 输入论文存在主题分散，需要主 Agent 决定是否继续探索。
- 需要调用子能力（检索、对比、洞察、idea、终稿润色）。

## Do not use this skill when
- 只需要导出原始论文列表。
- 只需要单篇论文摘要。

## Core rules
- 必须以“内容质量”决定是否停止，不得只因达到某轮数就停止。
- 必须覆盖四类结果：
  1. 今日更新论文（标题+链接）
  2. 创新点与同主题 baseline 差异
  3. 对领域的启发
  4. 后续可研究 idea（含依据）
- 必须优先沿主题聚类讨论，不做无意义横向对比。
- 当证据不足时，必须继续工具调用补证据。

## Standard workflow
1. 读取输入论文池与历史 memory。
2. 识别当天主线主题（2-4条）。
3. 调用检索工具补同主题上下文（近作+经典）。
4. 分配子任务：
   - `paper_scout`：筛主线与关键论文
   - `baseline_comparator`：做同主题比较
   - `insight_synthesizer`：提炼领域启发
   - `idea_generator`：生成可验证研究想法
   - `final_editor`：生成可读终稿
5. 执行质量门控，不达标则继续迭代。
6. 输出中文终稿。

## Validation checklist
- 包含论文标题和 arXiv 链接
- 每条主线都有 baseline 对比
- 结论有证据，不是空泛判断
- 中文可读性强，非短句堆砌
- 有明确下一步研究建议

## Failure handling
- 若检索结果少：放宽关键词后重搜。
- 若主题太散：先聚类再写作。
- 若报告泛泛：回到 comparator 和 synthesizer 补证据。

## Output requirements
- 中文 Markdown
- 结构化分节 + 段落化叙述
- 关键判断后附论文标识或链接
