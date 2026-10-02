---
name: self-loop
description: 自动迭代开发循环：发现 → 实现 → 测试 → 修复 → 提交，集成所有 self-* 技能
user_invocable: true
---

# Self-Loop — 自动迭代开发循环

集成所有 self-* 技能的完整自动化开发流水线。自动发现需求、实现代码、运行测试、修复问题、提交变更。

## 使用场景

| 模式 | 命令 | 说明 |
|------|------|------|
| **全自动** | `/self-loop` | 扫描项目 → 发现问题 → 逐个修复 |
| **功能开发** | `/self-loop 实现 X` | 跳过发现，直接实现指定功能 |
| **修复 Bug** | `/self-loop 修复 X` | 跳过发现，修复指定问题 |
| **补充测试** | `/self-loop 补充测试` | 发现未测试代码，逐个补充 |
| **项目维护** | `/self-loop 维护` | 扫描 HIGH/MEDIUM 问题，按优先级修复 |

## 集成流水线

```
┌──────────────────────────────────────────────────────────────────┐
│                    SELF-LOOP 集成流水线                            │
│                                                                  │
│  ┌──────────────┐                                                │
│  │ self-discover│ → 扫描项目，生成 backlog.md                     │
│  └──────┬───────┘                                                │
│         ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │self-implement│ →  │  self-test   │ →  │   验证结果    │       │
│  │  编写代码     │    │  运行测试     │    │  覆盖率检查   │       │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘       │
│                             │                   │                │
│                             ▼                   ▼                │
│                       ┌──────────────┐    ┌──────────────┐      │
│                       │   self-fix   │    │   完成？      │      │
│                       │  分析修复     │    └──────┬───────┘      │
│                       └──────────────┘           │               │
│                                                  │               │
│                            否 ◀──────────────────┴──────▶ 是    │
│                            │                            │        │
│                            ▼                            ▼        │
│                       [继续循环]                    [Git 提交]    │
│                                                  [处理下一个]    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 阶段 1: 发现 (self-discover)

扫描项目，识别待处理问题：

```bash
# 运行发现脚本
python scripts/discover.py

# 或使用 Claude Code 技能
/self-discover
```

读取生成的待办列表：

```bash
cat memory/backlog.md
```

优先级判断：

| 优先级 | 条件 | 处理方式 |
|--------|------|----------|
| HIGH | 安全漏洞、数据丢失风险 | 立即修复 |
| HIGH | 关键路径缺少错误处理 | 本次修复 |
| MEDIUM | 测试覆盖率 < 80% | 补充测试 |
| MEDIUM | 缺少输入验证 | 添加验证 |
| LOW | 代码风格、小改进 | 跳过或批量处理 |

## 阶段 2: 实现 (self-implement)

针对每个待办项：

1. **读取目标文件** — 完整理解上下文
2. **分析现有模式** — 匹配项目风格
3. **编写代码** — 遵循 CLAUDE.md 规范
4. **添加测试** — 覆盖正常和异常路径

项目规范要点：

- Python: PEP8、type hints、snake_case
- TypeScript: strict mode、返回类型、PascalCase 组件
- API 路由: `/api/xxx` 格式
- 所有外部调用必须有错误处理

## 阶段 3: 测试 (self-test)

运行完整测试套件：

```bash
# 后端测试 + 覆盖率
cd backend && python -m pytest tests/ -v --cov=backend --cov-report=term-missing --tb=short

# 前端测试
cd frontend && npm test -- --watchAll=false

# 快速反馈：运行单个测试文件
cd backend && python -m pytest tests/unit/test_services.py -v --tb=short

# 最快反馈：运行单个测试
cd backend && python -m pytest tests/unit/test_services.py::TestAIAnalyzer::test_analyze_news_success -v
```

覆盖率目标：

| 组件 | 目标 | 当前 |
|------|------|------|
| Models | 95% | ✅ |
| Database | 90% | ✅ |
| Services | 85% | ✅ |
| API endpoints | 80% | ✅ |
| Sources | 80% | ✅ |
| **总体** | **80%** | **86% ✅** |

## 阶段 4: 验证

测试通过后，检查质量：

- [ ] 所有测试通过
- [ ] 覆盖率 ≥ 80%
- [ ] 没有引入新警告
- [ ] 外部调用有错误处理
- [ ] 有 type hints
- [ ] 有 docstrings

## 阶段 5: 修复 (self-fix)

如果测试失败，分析并修复：

```bash
# 1. 从测试输出解析错误
# 2. 读取失败的测试文件
# 3. 读取被测试的源文件
# 4. 应用修复
# 5. 重新运行失败的测试
# 6. 通过后运行完整套件
```

常见修复模式：

| 错误类型 | 模式 | 修复方式 |
|----------|------|----------|
| AssertionError | 预期值错误 | 更新断言或修复逻辑 |
| TypeError | 缺少参数 | 修复函数签名 |
| ImportError | 导入路径错误 | 修复 import 语句 |
| AttributeError | NoneType 访问 | 添加空值检查 |
| KeyError | 缺少字典键 | 使用 .get() 带默认值 |
| AsyncMock 错误 | Mock 类型错误 | 响应用 MagicMock，方法用 AsyncMock |

每个失败最多 6 次修复尝试，超过则升级给用户。

## 阶段 6: 提交

所有测试通过后：

```bash
# 暂存变更
git add -A

# 使用约定格式提交
git commit -m "feat: {描述}

- {变更1}
- {变更2}

测试: {N} 通过, 覆盖率 {X}%"
```

提交消息前缀：

| 前缀 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 修复 Bug |
| `test:` | 添加测试 |
| `refactor:` | 代码重构 |
| `docs:` | 文档更新 |

## 循环控制

| 限制 | 值 | 原因 |
|------|-----|------|
| 最大迭代次数 | 20 | 防止无限循环 |
| 总时长超时 | 60 分钟 | 尊重用户时间 |
| 循环内执行超时 | 30 分钟 | 单次循环时间限制 |
| 单个失败最大修复次数 | 6 | 超过则升级 |
| 连续失败限制 | 3 | 检测卡住状态 |

## 记忆文件

循环读写多个记忆文件：

| 文件 | 用途 | 写入者 |
|------|------|--------|
| `memory/backlog.md` | 待处理工作项 | self-discover |
| `memory/test-report.md` | 最新测试结果 | self-test |
| `memory/fix-log.md` | 修复历史 | self-fix |
| `memory/changelog.md` | 已完成工作日志 | self-loop |
| `memory/decisions.md` | 架构决策记录 | self-loop |

## 输出：循环报告

每次运行后生成：

```markdown
# Self-Loop 报告 — YYYY-MM-DD HH:MM

## 模式: {全自动|功能|修复|维护|测试补充}

## 处理项目
- [x] 项目1: 添加邮件服务错误处理
- [x] 项目2: 修复 test_database_connection
- [ ] 项目3: 添加 API 验证 (已升级)

## 统计
- 迭代次数: 5
- 耗时: 12 分钟
- 修复前: 172 测试通过, 86% 覆盖率
- 修复后: 186 测试通过, 87% 覆盖率
- 完成项目: 2/3
- 升级项目: 1

## 变更文件
- backend/services/email_sender.py: 添加重试逻辑
- backend/tests/unit/test_email_sender.py: 新增 4 个测试
- backend/services/database.py: 修复连接清理

## 升级项
### 项目3: 添加 API 验证
- 原因: 6 次修复尝试耗尽
- 错误: Pydantic validator 未触发
- 建议: 检查 Pydantic 版本兼容性
```

## 执行示例

### 全自动维护
```
/self-loop
```
执行完整流水线：发现 → 优先级排序 → 实现 → 测试 → 修复 → 提交

### 功能开发
```
/self-loop 实现 RSS 订阅源
```
跳过发现阶段，实现功能并迭代测试修复

### 修复 Bug
```
/self-loop 修复 test_push_notification 失败
```
针对特定失败，迭代直到修复

### 补充测试
```
/self-loop 补充测试
```
发现未测试代码，逐个生成测试

### 项目维护
```
/self-loop 维护
```
扫描 HIGH/MEDIUM 问题，按优先级修复
