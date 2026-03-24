# DailyPaperAgent

DailyPaperAgent 是一个用于论文追踪与日报生成的 Agent 工作流项目。

它不是“抓论文 + 套模板摘要”的固定流水线，而是把主控 Agent、角色化子 Agent、轻量记忆和质量闸门结合起来，让系统能够在运行中自行搜索、比较、归纳、修订，并判断何时可以输出终稿。

## 它能做什么

- 从 arXiv 抓取指定主题范围内的最新论文，构建较大的探索池
- 让主 Agent 自行决定何时继续搜索、何时调用记忆、何时调用子 Agent
- 生成中文 Markdown 日报，并可渲染成 PDF
- 可选地通过邮件发送日报
- 跨轮次保存轻量记忆，包括已读论文、趋势线索和 idea backlog

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

复制本地配置：

```bash
cp config.example.yaml config.yaml
```

先 dry-run：

```bash
python main.py --config config.yaml --once --dry-run
```

单次真实运行：

```bash
python main.py --config config.yaml --once
```

持续调度运行：

```bash
python main.py --config config.yaml
```

## 需要配置什么

本地只需要准备一个 `config.yaml`。这个文件已经被 Git 忽略，不会默认提交。

主要配置项包括：

- `llm`：模型 API key、base URL、model name
- `topics`：arXiv 分类、包含关键词、排除关键词
- `arxiv`：候选池大小、回看时间窗口
- `scheduler`：运行间隔、探索池大小、分析池大小
- `report`：Agent step 上限、润色轮数、上下文预算
- `mail`：可选的 SMTP 邮件发送设置

推荐使用环境变量管理敏感信息：

```bash
export MINIMAX_API_KEY="你的 API Key"
export MAIL_USERNAME="发件邮箱账号"
export MAIL_PASSWORD="邮箱授权码"
export MAIL_FROM_ADDR="发件邮箱地址"
```

## 如何迁移到其他主题

这个项目并不绑定某一个具体研究方向。通常只需要调整这些部分，就可以迁移到新的主题：

- 修改 arXiv 分类
- 修改 include / exclude 关键词
- 增加自己的 domain preset
- 调整探索池大小和 Agent step 预算

也就是说，它更像一个“可配置的研究主题雷达”，而不是只服务某一个课题。

如果你想针对某个方向做更强的定制，可以在本地 `config.yaml` 中改 topic，或者增加自己的 domain preset。

## 输出结果

- Markdown 日报：`reports/`
- PDF 日报：`reports/`
- 状态记忆：`data/state.json`
- 运行日志：`runtime_logs/`
