# 简历项目优化 Agent

一个基于本地 `hello_agents` 包的可交互简历项目优化工具。它会通过多轮追问收集项目材料，再生成简历项目简介、bullet、技术亮点、面试追问、评分卡和补强建议。

## hello_agents 用法

- `HelloAgentsLLM`：统一连接 DeepSeek/OpenAI 兼容模型。
- `SimpleAgent`：承担项目追问、项目分析、简历改写、评分审核。
- `ToolRegistry`：注册工具给 Agent 使用。
- `NoteTool`：把初始材料、用户回答、分析结果、最终报告保存为结构化笔记。
- `ContextBuilder`：把多轮问答和笔记压成结构化上下文。
- `ReflectionAgent`：对简历初稿进行反思、审稿和改写。

## 运行

```powershell
cd "D:\codex_nigr\New project 5"
D:\python02\python.exe -m pip install -r requirements.txt
copy .env.example .env
D:\python02\python.exe main.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

默认是离线演示模式，不需要 API key。要真实调用 DeepSeek，把 `.env` 改成：

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=你的DeepSeekKey
LLM_BASE_URL=https://api.deepseek.com/v1
```

## 流程

1. 前端提交项目名称、目标岗位、技术栈、原始描述。
2. `项目追问Agent` 分阶段提出问题。
3. 每次回答都会通过 `NoteTool` 写入 `data/notes`。
4. `项目分析Agent` 使用 `ContextBuilder` 汇总多轮材料，输出项目分析结构。
5. `简历改写Agent` 生成简历优化包。
6. `ReflectionAgent` 审稿并尝试改进最终结果。
7. 前端展示简历稿、技术亮点、面试追问和评分卡。
