# Resume Project Optimizer Agent

[English README](./README.md)

一个基于本地 `hello_agents` 包构建的交互式简历项目优化系统。

它的目标是把用户一段模糊、零散的项目描述，逐步整理成更适合写进简历、也更适合面试展开的项目表述。

## 项目功能

- 通过多轮追问收集项目信息，而不是一开始一次性让用户填写所有内容
- 将追问流程拆成四个阶段：项目定位、个人职责、技术难点、结果量化
- 使用 `NoteTool` 保存结构化会话记忆，而不是只依赖原始对话历史
- 使用 `ContextBuilder` 将多轮问答与笔记压缩成后续 Agent 可消费的上下文
- 生成完整的简历优化结果，包括项目简介、简历 bullet、技术亮点、架构要点、结果表述和面试追问
- 在最终输出前通过反思式审核，削弱证据不足的表述，提升结果可信度

## 这个项目解决了什么问题

很多人在写简历项目时会遇到一个典型问题：

- 知道自己做了什么，但说不清项目到底解决了谁的问题
- 能讲功能，却讲不清自己亲自负责了哪些部分
- 能写技术名词，但讲不清关键设计决策和难点
- 容易把项目写得空泛，或者在面试里撑不住细问

这个项目的作用，就是把“模糊项目描述”逐步变成“结构化、可防守、可面试展开”的简历项目内容。

## 系统概览

后端基于 FastAPI，前端是轻量静态页面，核心工作流由多个基于 `hello_agents` 的 Agent 协同完成。

### 核心组件

- `HelloAgentsLLM`
  统一连接 DeepSeek 或 OpenAI 兼容模型。

- `SimpleAgent`
  用于项目追问、结构分析和简历内容生成。

- `ReflectionAgent`
  用于最终结果的证据审查与反思式改写。

- `ToolRegistry`
  用于注册 Agent 可调用的工具。

- `NoteTool`
  用于保存初始输入、用户回答、分析结果和最终输出等结构化笔记。

- `ContextBuilder`
  用于把原始描述、多轮回答和笔记记录整合成更紧凑的上下文。

## Agent 工作流

### 1. 项目追问 Agent

`DiscoveryAgent` 会分阶段向用户追问，而不是一次性抛出很多问题。

当前阶段包括：

- `overview`
- `role`
- `technical`
- `impact`

它在一次 LLM 调用中同时完成两件事：

- 理解用户最新回答
- 判断这轮回答属于 `skip`、`unknown_only`、`informative` 还是 `informative_with_unknown`
- 提取可用事实和不确定项
- 决定当前阶段是否继续追问，还是进入下一阶段

这样做的好处是，不需要额外新增一个“回答理解 Agent”，可以在控制 token 成本的同时提升流程智能度。

### 2. 记忆层

项目中的重要交互都会通过 `NoteTool` 记录为结构化记忆，包括：

- 初始项目描述
- 每轮回答及其回答意图
- 提取出的有效事实
- 不确定或缺失的信息
- 项目分析结果
- 最终简历优化包

这样后续 Agent 获取到的就不只是聊天记录，而是更结构化、更适合推理的上下文材料。

### 3. 项目分析 Agent

`ProjectAnalyzerAgent` 会结合当前会话状态和 NoteTool 笔记，输出结构化分析结果，例如：

- 项目问题定义
- 使用场景
- 个人职责
- 技术栈
- 技术挑战
- 解决方案
- 结果
- 风险点
- 缺失信息

### 4. 简历改写 Agent

`ResumeWriterAgent` 会把结构化分析转换成更适合简历表达的输出包，包括：

- 项目定位
- 项目简介
- 简历 bullet
- 技术亮点
- 架构要点
- 结果表述
- 面试追问
- 下一步补强建议

### 5. 审核 Agent

`ResumeCriticAgent` 会结合反思流程和上下文工程，对生成结果进行二次审阅。

它的核心职责是：

- 删除或弱化证据不足的表述
- 将不确定内容移入缺失信息区
- 提高整体表达的清晰度和面试可辩护性

## 端到端流程

```text
用户输入
  -> FastAPI 创建会话
  -> DiscoveryAgent 分阶段追问
  -> NoteTool 写入结构化记忆
  -> ProjectAnalyzerAgent 生成项目分析
  -> ResumeWriterAgent 生成简历优化包
  -> ResumeCriticAgent 做证据审核与改写
  -> 前端展示最终结果 / 流式输出
```

## 技术栈

- Python
- FastAPI
- Pydantic
- Uvicorn
- JavaScript
- `hello_agents`
- DeepSeek API / OpenAI 兼容 API

## 项目结构

```text
.
├─ main.py
├─ requirements.txt
├─ src
│  ├─ app.py
│  ├─ config.py
│  ├─ llm.py
│  ├─ models.py
│  ├─ agents
│  │  ├─ base.py
│  │  ├─ discovery.py
│  │  ├─ analyzer.py
│  │  ├─ writer.py
│  │  └─ critic.py
│  ├─ services
│  │  ├─ workflow.py
│  │  ├─ session_store.py
│  │  └─ memory_store.py
│  └─ utils
│     └─ json_utils.py
└─ static
   ├─ index.html
   ├─ app.js
   └─ styles.css
```

## 本地运行

### 1. 安装依赖

```powershell
cd "D:\codex_nigr\New project 5"
D:\python02\python.exe -m pip install -r requirements.txt
```

### 2. 创建本地环境变量文件

```powershell
copy .env.example .env
```

### 3. 启动项目

```powershell
D:\python02\python.exe main.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 大模型配置

项目支持离线演示模式和真实大模型模式。

### 离线演示模式

```env
LLM_ENABLED=false
```

### DeepSeek 实际调用模式

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.deepseek.com/v1
```

## 接口列表

- `GET /api/health`
- `POST /api/session/start`
- `POST /api/session/submit`
- `POST /api/session/{session_id}/finalize`
- `POST /api/session/{session_id}/finalize/stream`
- `GET /api/session/list`
- `GET /api/session/{session_id}`
- `DELETE /api/session/{session_id}`
- `DELETE /api/session/all`
- `GET /api/notes/summary`

## 适合简历展开的设计点

这个项目比较适合在简历和面试里展开这些工程点：

- 分阶段 Agent 工作流，而不是一条大 Prompt 一把梭
- 工具化记忆管理，而不是只靠原始对话上下文
- 基于 `ContextBuilder` 的上下文工程
- 面向证据的结果审核，而不是单纯“美化语言”
- 在 Agent 自主性和确定性流程控制之间做平衡

## 当前局限

- 输出质量仍然依赖用户输入的真实性和完整度
- 目前还没有做正式的用户认证或多用户隔离
- 前端重点在工作流可用性，而不是完整产品化设计
- 证据审查能力强于普通 Prompt，但还不是严格意义上的事实校验系统

## 后续可扩展方向

- 导出 Markdown 或 Word 版本结果
- 对每条 bullet 增加更细粒度的证据评分
- 支持上传截图、项目文档、PR 链接等作为补充证据
- 增强前端对阶段记忆与推理过程的可视化展示
- 增加追问质量和阶段完成效率的分析统计
