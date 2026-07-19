# ResearchPilot

学术论文检索与管理平台

## 技术栈

### 前端
- Vue 3 + TypeScript
- Vite
- Vue Router
- Pinia
- Axios
- Element Plus

### 后端
- Python 3.12
- FastAPI
- SQLAlchemy 2.0
- Pydantic v2
- Alembic
- MySQL
- JWT

## 项目结构

```
ResearchPilot/
├── frontend/          # Vue3 前端
├── backend/           # FastAPI 后端
├── docs/              # 项目文档
├── docker/            # Docker 配置
└── scripts/           # 工具脚本
```

## 快速开始

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
