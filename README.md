# Layer - 智能法律咨询助手

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-0.116+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-0.6+-orange.svg" alt="LangGraph">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
</p>

<p align="center">
  <b>基于多智能体协作的智能法律咨询系统</b><br>
  <i>Multi-Agent AI Legal Consultation System powered by LangGraph & RAG</i>
</p>
---

## 🎯 项目简介

Layer 是一个面向法律咨询场景的智能多智能体工作流系统。它基于 **LangGraph** 构建多角色协作流程，结合 **RAG（检索增强生成）** 技术，为用户提供专业、准确的法律咨询服务。

### ✨ 核心特性

- 🤖 **多智能体协作**：律师助理、领域路由、案情摘要、律师分析四大智能体协同工作
- 📚 **RAG 检索增强**：基于法律知识库的混合检索（BM25 + FAISS + 重排序）
- ⚡ **流式响应**：SSE 实时流式输出，提升用户体验
- 🏗️ **模块化架构**：工作流、检索、存储、配置等模块职责清晰
- 📱 **响应式界面**：支持桌面端和移动端访问
- 🔒 **安全设计**：RAG 约束防止幻觉，XSS 防护确保输出安全

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         用户界面层                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  任务管理   │  │  消息展示   │  │    Markdown渲染     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      FastAPI 服务层                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              /send_message_stream                   │    │
│  │                  SSE 流式接口                        │    │
│  └────────────────────────┬────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   LangGraph 工作流引擎                       │
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │  欢迎节点 │───▶│ 用户输入  │───▶│ 律师助理  │            │
│   │  Greet   │    │  Client  │    │ Paralegal│            │
│   └──────────┘    └──────────┘    └────┬─────┘            │
│                                         │                   │
│   ┌──────────┐    ┌──────────┐    ┌─────▼─────┐           │
│   │  律师分析 │◀───│ 案情摘要  │◀───│  路由节点  │           │
│   │  Lawyer  │    │ Summary  │    │  Router  │           │
│   └────┬─────┘    └──────────┘    └──────────┘           │
│        │                                                    │
│        └──────────────────────────────────────▶ 用户        │
│                                                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    RAG 检索系统                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  BM25检索   │  │ FAISS向量   │  │  Cross-Encoder     │  │
│  │  (关键词)   │  │  (语义)     │  │     重排序          │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
│         │                │                                  │
│         └────────┬───────┘                                  │
│                  ▼                                          │
│         ┌─────────────────┐                                 │
│         │   法律知识库     │                                 │
│         │  (多领域索引)   │                                 │
│         └─────────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Redis 6.0+
- OpenAI API Key 或兼容的 API 服务

### 安装步骤

1. **克隆仓库**

```bash
git clone https://github.com/MMoon007/layer-multiagent.git
cd layer-multiagent
```

2. **创建虚拟环境**

```bash
conda create -n layer python=3.12
conda activate layer
```

3. **安装依赖**

```bash
pip install -r requirements.txt
```

4. **配置环境**

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，填写你的 API 密钥和配置
```

5. **启动 Redis**（如果没有运行）

```bash
# Windows
cd redis/redis-8.0.0
./redis-server.exe

# Linux/Mac
redis-server
```

6. **启动应用**

```bash
# 本地启动
python -m main.app

# 或使用脚本
./local.sh
```

访问 http://localhost:8000 即可使用。

---

## ⚙️ 配置说明

创建 `config.yaml` 文件，参考以下结构：

```yaml
openai:
  # API 基础地址
  api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  # API 密钥（请替换为您的实际密钥）
  api_key: ""
  # 使用的模型
  model: "qwen3.5"
  # 温度参数（0-2，越高越随机）
  temperature: 0.1

# Redis 配置
redis:
  # Redis 服务器地址
  host: "127.0.0.1"
  # Redis 服务器端口
  port: 6379

rag:
  folder_path: "./rag_data"
  index_path: "./faiss_index"
  embedding_model: "Qwen/Qwen3-Embedding-0.6B"
  rerank_model: "BAAI/bge-reranker-base"
  device: "cpu"  # 或 "cuda"
```

---

## 📚 法律知识库

将法律文档放入 `rag_data/` 目录下的对应文件夹中：

```
rag_data/
├── 刑法/
├── 宪法相关法/
├── 民法商法/
├── 社会法/
├── 经济法/
├── 行政法/
└── 诉讼与非诉讼程序法/
```

支持的文档格式：
- PDF (`.pdf`)
- 文本文件 (`.txt`)
- Word 文档 (`.docx`)

系统会自动构建索引并检测文档变更。

---

## 🛠️ 技术栈

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| **FastAPI** | 0.116+ | Web 框架 |
| **LangGraph** | 0.6+ | 多智能体工作流编排 |
| **LangChain** | 0.3+ | LLM 应用框架 |
| **FAISS** | 1.12+ | 向量检索 |
| **Redis** | 6.0+ | 会话存储 |

### 前端
| 技术 | 用途 |
|------|------|
| **原生 JavaScript** (ES6+) | 交互逻辑 |
| **CSS3** | 样式设计 |
| **Font Awesome** | 图标库 |
| **Markdown-it** | Markdown 渲染 |
| **DOMPurify** | XSS 防护 |

---

## 📁 项目结构

```
layer/
├── main/
│   ├── app.py                 # FastAPI 主应用
│   ├── legal_workflow.py      # 法律工作流核心
│   ├── rag.py                 # RAG 检索系统
│   ├── prompt.py              # 提示词模板
│   ├── chatstore.py           # 会话存储
│   ├── config.py              # 配置管理
│   ├── templates/
│   │   ├── index.html         # 主界面
│   │   └── admin.html         # 管理后台
│   └── static/
│       ├── layer.css          # 样式文件
│       ├── layer.js           # 前端逻辑
│       └── user-storage.js    # 用户存储
├── rag_data/                  # 法律知识库
├── config.yaml                # 配置文件
├── requirements.txt           # Python 依赖
└── local.sh                   # 启动脚本
```

---

## 🔧 核心模块

### 1. 多智能体工作流 (legal_workflow.py)

基于 LangGraph 构建的工作流，包含四个智能体：

- **律师助理 (Paralegal)**：接待当事人，结构化收集案情信息
- **路由 (Router)**：判断案件所属法律领域
- **摘要 (Summary)**：提炼关键信息生成结构化摘要
- **律师 (Lawyer)**：结合 RAG 检索给出专业法律分析

### 2. RAG 检索系统 (rag.py)

- **混合检索**：BM25 + FAISS 向量检索
- **重排序**：Cross-Encoder 优化结果排序
- **多领域管理**：按法律领域组织独立索引
- **懒加载**：按需初始化，节省资源

### 3. 提示词管理 (prompt.py)

包含完整的提示词模板：
- 律师助理角色设定
- 领域路由判断
- 案情摘要生成
- 律师分析（含 RAG 约束）

---

## 🌐 部署

### 本地部署

```bash
./local.sh
```

