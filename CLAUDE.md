# Mr.Sheven - 酒类评测速查项目

## 项目结构

```
Mr.Sheven/
├── shared/          # 共享模块：models(SQLAlchemy)、config、LLM客户端、清洗/归一化工具
├── pipeline/        # 离线批处理（入口 python -m pipeline.scheduler）
│   ├── crawler/     # B站视频列表爬取
│   ├── subtitle/    # AI字幕获取
│   ├── cleaner/     # 文本清洗
│   ├── dedup/       # 三层查重
│   ├── llm/         # LLM结构化提取与对比研判
│   └── normalize/   # SPU归一化入库
├── server/          # FastAPI查询服务（入口 uvicorn server.main:app）
│   ├── api/         # 路由定义
│   └── middleware/   # 缓存 + 限流
├── alembic/         # 数据库迁移（alembic upgrade head）
├── tests/           # 测试
├── deploy/          # Docker Compose、nginx
├── docs/            # 项目文档
├── app/             # Flutter 前端
└── probe/           # 探针实验物料
```

## 测试命令

```bash
python -m pytest tests/ -v --tb=short
```

## 代码规范

- Python 3.12+
- 命名：snake_case
- 类型提示：所有公共函数必须有 type hints
- 代码风格：ruff (line-length=100)
- 提交规范：feat/fix/refactor/docs

## 技术栈

- 后端：FastAPI + SQLAlchemy + MySQL 8.0 + Redis
- 客户端：Flutter（原生App）
- LLM：百炼 qwen-plus
- MVP仅扫码（条形码），不做OCR和ASR