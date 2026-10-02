# Claude 自动化开发工具集

本目录包含可移植的 Claude Code 技能和工作流配置。

## 目录结构

```
.claude/
├── skills/                    # 技能（实时执行）
│   ├── self-loop-adv.md      # 增强版自动迭代（推荐）
│   ├── adversarial-dev.md    # 轻量级对抗性开发
│   ├── self-discover.md      # 问题发现
│   ├── self-implement.md     # 自动实现
│   ├── self-test.md          # 自动测试
│   ├── self-fix.md           # 自动修复
│   ├── self-loop.md          # 基础自动迭代
│   ├── assets/               # 资产文件
│   └── references/           # 参考文档
├── workflows/                 # 工作流（后台执行）
│   ├── self-loop-adv.js      # 增强版自动迭代
│   └── adversarial-dev.js    # 对抗性开发
└── README.md                 # 本文件
```

## 快速开始

### 1. 复制到你的项目

```bash
cp -r .claude/ /path/to/your/project/
```

### 2. 配置测试命令

编辑技能文件，修改测试命令：

**self-loop-adv.md（第 38-39 行）**
```bash
# 后端测试
python -m pytest tests/ -v --cov=src --tb=short

# 前端测试（如果存在）
cd frontend && npm test -- --watchAll=false
```

### 3. 使用技能

```bash
# 自动发现模式
/self-loop-adv

# 多需求模式
/self-loop-adv "需求1; 需求2; 需求3"

# 从文件读取
/self-loop-adv "@requirements.txt"

# 轻量级版本
/adversarial-dev "需求1; 需求2; 需求3"
```

## 技能 vs 工作流

| 特性 | 技能 (Skill) | 工作流 (Workflow) |
|------|-------------|------------------|
| 运行方式 | 当前窗口实时滚动 | 后台运行 |
| 查看过程 | ✅ 实时可见 | ❌ 完成后才显示 |
| 交互性 | 可随时中断 | 需要 TaskStop |
| 适用场景 | 开发调试、学习过程 | 批量任务、无人值守 |

## 执行流程

### self-loop-adv（增强版）

每个需求依次执行：
1. **实现** → 编写代码和测试
2. **测试** → 运行测试套件（失败自动修复，最多 3 次）
3. **对抗性审查** → 并行审查逻辑、测试、安全性
4. **修复** → 修复审查发现的问题
5. **提交** → 自动 git commit

最后生成执行报告。

### adversarial-dev（轻量级）

每个需求依次执行：
1. **实现** → 编写代码和测试
2. **对抗性审查** → 并行审查逻辑和测试
3. **修复** → 修复审查发现的问题
4. **提交** → 自动 git commit

## 配置说明

### 覆盖率要求

在技能文件中修改覆盖率要求：
- 核心模块: > 95%
- 服务层: > 80%
- API 层: > 75%

### 项目规范

根据项目调整命名规范和提交规范：
- Python: snake_case
- TypeScript: PascalCase（组件）/ camelCase（工具函数）
- 提交: feat/fix/refactor/docs

## 错误处理

- 单个需求失败不影响后续需求继续执行
- 测试失败会自动尝试修复（最多 3 次）
- 审查发现的问题会立即修复
- 所有错误都会记录在执行报告中

## 移植到其他项目

1. 复制整个 `.claude/` 目录
2. 修改技能文件中的测试命令
3. 根据项目调整配置
4. 开始使用

## 示例

### 示例 1: 自动发现并修复问题

```bash
/self-loop-adv
```

自动扫描 `memory/backlog.md`，按优先级处理每个问题。

### 示例 2: 批量实现功能

```bash
/self-loop-adv "添加用户登录; 实现权限管理; 优化查询性能"
```

依次实现三个功能，每个完成后自动提交。

### 示例 3: 从文件读取需求

创建 `requirements.txt`：
```
# 用户管理模块
添加用户注册功能
实现密码重置

# 性能优化
优化数据库查询
添加缓存机制
```

然后执行：
```bash
/self-loop-adv "@requirements.txt"
```

## 常见问题

### Q: 如何修改测试命令？

A: 编辑技能文件，找到测试命令部分（通常在"阶段 2: 测试"），修改为你的项目测试命令。

### Q: 如何跳过测试？

A: 在需求描述中添加 `[skip-test]` 标记，或修改技能文件跳过测试阶段。

### Q: 如何查看执行历史？

A: 执行完成后会自动生成报告。也可以查看 git log 了解提交历史。

### Q: 工作流和技能有什么区别？

A: 技能在当前窗口实时显示过程，工作流在后台运行。开发调试建议用技能，批量任务用工作流。
