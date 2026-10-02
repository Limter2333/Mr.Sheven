---
name: self-discover
description: 自动扫描项目，发现待办事项、技术债务、缺失测试、潜在改进。支持多维度分析和优先级排序。
user_invocable: true
---

# Self-Discover — 自动发现待办事项

## 使用场景
- 开始新会话时，快速了解项目状态
- 寻找可以改进的地方
- 生成待办事项清单
- 评估代码质量和测试覆盖

## 执行流程

```
1. 项目结构分析
   ├── 扫描目录结构
   ├── 统计文件数量
   └── 识别核心模块

2. 代码质量扫描
   ├── TODO/FIXME/HACK 注释
   ├── 空 except 块
   ├── 未使用的导入
   ├── 缺失的类型提示
   └── 缺失的 docstring

3. 测试覆盖分析
   ├── 检查测试文件存在性
   ├── 运行覆盖率统计
   └── 识别低覆盖率模块

4. 安全扫描
   ├── 硬编码密钥
   ├── 不安全的函数
   └── 未处理的异常

5. 依赖分析
   ├── 过时的依赖
   ├── 缺失的依赖
   └── 版本冲突

6. 生成报告
   ├── 按优先级排序
   ├── 提供修复建议
   └── 写入 backlog.md
```

## 扫描维度

### 1. 项目结构分析

```bash
# 统计项目文件
echo "=== 项目结构 ==="
find . -type f -name "*.py" -o -name "*.ts" -o -name "*.tsx" | grep -v node_modules | grep -v __pycache__ | wc -l

# 识别核心模块
echo "=== 核心模块 ==="
ls -la backend/services/
ls -la backend/sources/
ls -la frontend/src/components/

# 检查目录结构完整性
echo "=== 目录检查 ==="
[ -d "backend/tests" ] && echo "✓ 后端测试目录" || echo "✗ 缺少后端测试目录"
[ -d "frontend/src/test" ] && echo "✓ 前端测试目录" || echo "✗ 缺少前端测试目录"
[ -f "CLAUDE.md" ] && echo "✓ 项目指南" || echo "✗ 缺少 CLAUDE.md"
```

### 2. 代码质量扫描

#### 2.1 TODO/FIXME 注释

```bash
# 查找所有 TODO/FIXME/HACK/XXX 注释
echo "=== TODO/FIXME 注释 ==="
grep -rn "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.ts" --include="*.tsx" . 2>/dev/null | grep -v node_modules | grep -v __pycache__
```

#### 2.2 异常处理问题

```bash
# 查找空的 except 块
echo "=== 空 except 块 ==="
grep -rn "except:" --include="*.py" . -A1 2>/dev/null | grep -v node_modules

# 查找过于宽泛的异常捕获
echo "=== 宽泛异常捕获 ==="
grep -rn "except Exception" --include="*.py" . 2>/dev/null | grep -v node_modules

# 查找未处理的异常
echo "=== 未处理异常 ==="
grep -rn "raise" --include="*.py" . 2>/dev/null | grep -v "raise\|#" | head -20
```

#### 2.3 代码风格问题

```bash
# 查找未使用的导入（需要 pyflakes）
echo "=== 未使用的导入 ==="
python -m pyflakes . 2>/dev/null | grep "imported but unused" | head -20

# 查找过长的行（>120字符）
echo "=== 过长的行 ==="
find . -name "*.py" -exec awk 'length > 120 {print FILENAME ":" NR ": " $0}' {} \; 2>/dev/null | head -20

# 查找重复代码（简单检查）
echo "=== 可能的重复代码 ==="
find . -name "*.py" -exec md5sum {} \; 2>/dev/null | sort | uniq -d
```

#### 2.4 类型提示和文档

```bash
# 查找缺失类型提示的函数
echo "=== 缺失类型提示的函数 ==="
grep -rn "def " --include="*.py" . 2>/dev/null | grep -v "->" | grep -v "__" | grep -v test | head -20

# 查找缺失 docstring 的类
echo "=== 缺失 docstring 的类 ==="
python3 -c "
import ast
import os

for root, dirs, files in os.walk('.'):
    if 'node_modules' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py') and not file.startswith('test_'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        if not ast.get_docstring(node):
                            print(f'{filepath}:{node.lineno}: class {node.name} - 缺失 docstring')
            except:
                pass
" 2>/dev/null | head -20
```

### 3. 测试覆盖分析

#### 3.1 测试文件存在性检查

```bash
# 检查后端测试文件
echo "=== 后端测试覆盖 ==="
for f in backend/services/*.py; do
    if [ "$(basename $f)" = "__init__.py" ]; then
        continue
    fi
    test_file="backend/tests/unit/test_$(basename $f)"
    if [ -f "$test_file" ]; then
        echo "✓ $f -> $test_file"
    else
        echo "✗ $f -> 缺少测试"
    fi
done

# 检查新闻源测试
for f in backend/sources/*.py; do
    if [ "$(basename $f)" = "__init__.py" ] || [ "$(basename $f)" = "base.py" ]; then
        continue
    fi
    test_file="backend/tests/unit/test_sources.py"
    if [ -f "$test_file" ]; then
        echo "✓ $f -> test_sources.py (包含测试)"
    else
        echo "✗ $f -> 缺少测试"
    fi
done

# 检查前端测试文件
echo "=== 前端测试覆盖 ==="
for f in frontend/src/components/*.tsx; do
    component_name=$(basename $f .tsx)
    test_file="frontend/src/components/__tests__/${component_name}.test.tsx"
    if [ -f "$test_file" ]; then
        echo "✓ $f -> $test_file"
    else
        echo "✗ $f -> 缺少测试"
    fi
done
```

#### 3.2 运行覆盖率统计

```bash
# 运行后端测试并生成覆盖率报告
echo "=== 后端测试覆盖率 ==="
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing 2>/dev/null | tail -30

# 运行前端测试
echo "=== 前端测试结果 ==="
cd frontend && npm test 2>/dev/null | tail -10
```

#### 3.3 低覆盖率模块识别

```bash
# 识别覆盖率低于 80% 的模块
echo "=== 低覆盖率模块 ==="
python -m pytest backend/tests/ --cov=backend --cov-report=json 2>/dev/null
python3 -c "
import json
try:
    with open('coverage.json') as f:
        cov = json.load(f)
    for f, data in cov.get('files', {}).items():
        pct = data.get('summary', {}).get('percent_covered', 0)
        if pct < 80 and 'test' not in f and '__init__' not in f:
            print(f'⚠️  {f}: {pct:.1f}%')
except:
    print('无法读取覆盖率报告')
" 2>/dev/null
```

### 4. 安全扫描

```bash
# 查找硬编码的密钥/密码
echo "=== 安全问题 ==="
grep -rn "password\|secret\|api_key\|token\|credential" --include="*.py" --include="*.ts" --include="*.tsx" . 2>/dev/null | grep -v node_modules | grep -v __pycache__ | grep -v test | grep -v ".example" | grep -v "#"

# 查找不安全的函数
echo "=== 不安全的函数 ==="
grep -rn "eval(\|exec(\|os.system(\|subprocess.call(" --include="*.py" . 2>/dev/null | grep -v node_modules | grep -v test

# 查找 SQL 注入风险
echo "=== SQL 注入风险 ==="
grep -rn "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE" --include="*.py" . 2>/dev/null | grep -v node_modules

# 查找未验证的用户输入
echo "=== 未验证的输入 ==="
grep -rn "request\.\|input(" --include="*.py" . 2>/dev/null | grep -v "validate\|check\|assert" | head -10
```

### 5. 依赖分析

```bash
# 检查 Python 依赖
echo "=== Python 依赖 ==="
pip list --outdated 2>/dev/null | head -20

# 检查 npm 依赖
echo "=== npm 依赖 ==="
cd frontend && npm outdated 2>/dev/null | head -20

# 检查 requirements.txt 是否最新
echo "=== requirements.txt 检查 ==="
if [ -f "requirements.txt" ]; then
    echo "requirements.txt 存在"
    # 检查是否有未声明的依赖
    pip freeze 2>/dev/null | grep -v "^\s*#" | sort > /tmp/installed.txt
    sort requirements.txt > /tmp/required.txt
    comm -23 /tmp/installed.txt /tmp/required.txt | head -10
fi
```

### 6. 性能分析

```bash
# 查找潜在的性能问题
echo "=== 性能问题 ==="

# N+1 查询问题
grep -rn "for.*in.*:" --include="*.py" . -A5 2>/dev/null | grep -B1 "await\|query\|fetch" | head -10

# 大型循环
grep -rn "for.*in.*range(1000\|for.*in.*range(10000" --include="*.py" . 2>/dev/null | head -5

# 未优化的数据库查询
grep -rn "SELECT \* FROM" --include="*.py" . 2>/dev/null | head -5
```

## 输出格式

写入 `memory/backlog.md`：

```markdown
# 项目待办事项 — YYYY-MM-DD

## 📊 项目概览
- **总文件数**: X 个 Python 文件, Y 个 TypeScript 文件
- **测试覆盖**: Z% (后端), W% (前端)
- **代码质量**: N 个 TODO, M 个安全问题

## 🔴 高优先级 (必须修复)

### 安全问题
1. [ ] [安全] backend/main.py:15 — 硬编码 API Key，应移至环境变量
   - **影响**: 敏感信息泄露
   - **修复**: 使用 `os.getenv()` 或 `pydantic-settings`

### 测试缺失
2. [ ] [测试] backend/services/news_aggregator.py — 缺少单元测试
   - **影响**: 代码变更无法验证
   - **修复**: 创建 `backend/tests/unit/test_news_aggregator.py`

### 异常处理
3. [ ] [质量] backend/sources/finance.py:45 — 空 except 块
   - **影响**: 错误被静默吞掉
   - **修复**: 添加日志记录或具体异常类型

## 🟡 中优先级 (建议修复)

### 代码质量
4. [ ] [质量] backend/services/ai_analyzer.py — 覆盖率仅 64%
   - **影响**: AI 分析逻辑未充分测试
   - **修复**: 添加 mock 测试 AI API 调用

5. [ ] [质量] backend/database.py:171-172 — 未处理的异常
   - **影响**: 数据库错误可能导致崩溃
   - **修复**: 添加 try-except 和错误日志

### 文档缺失
6. [ ] [文档] backend/services/ — 多个类缺少 docstring
   - **影响**: 代码可维护性差
   - **修复**: 添加类和方法的 docstring

## 🟢 低优先级 (可选优化)

### 性能优化
7. [ ] [优化] backend/services/news_aggregator.py — 可以并行处理新闻源
   - **影响**: 聚合速度慢
   - **修复**: 使用 `asyncio.gather()` 并行调用

### 代码风格
8. [ ] [风格] frontend/src/components/ — 部分组件缺少类型定义
   - **影响**: TypeScript 类型安全
   - **修复**: 添加 Props 接口定义

## 📈 统计详情

### 测试覆盖
| 模块 | 覆盖率 | 状态 |
|------|--------|------|
| models.py | 100% | ✅ 优秀 |
| database.py | 98% | ✅ 优秀 |
| briefing_generator.py | 100% | ✅ 优秀 |
| news_aggregator.py | 100% | ✅ 优秀 |
| scheduler.py | 97% | ✅ 优秀 |
| email_sender.py | 98% | ✅ 优秀 |
| push_notifier.py | 96% | ✅ 优秀 |
| ai_analyzer.py | 64% | ⚠️ 需改进 |
| sources/*.py | 15-21% | ⚠️ 需改进 |

### 代码质量
- TODO/FIXME 注释: N 个
- 空 except 块: M 个
- 缺失类型提示: X 个函数
- 缺失 docstring: Y 个类

### 安全问题
- 硬编码密钥: 0 个 ✅
- 不安全函数: 0 个 ✅
- SQL 注入风险: 0 个 ✅
```

## 优先级判断规则

### 🔴 高优先级
- 安全问题（硬编码密钥、SQL 注入、XSS）
- 测试缺失（核心模块无测试）
- 运行时错误风险（空 except、未处理异常）
- 数据丢失风险

### 🟡 中优先级
- 测试覆盖率低（<80%）
- 代码质量差（重复代码、复杂度过高）
- 文档缺失
- 性能问题

### 🟢 低优先级
- 代码风格问题
- 可选的优化
- 依赖更新
- 文档完善

## 自动执行

### 方式一：使用脚本（推荐）

```bash
# 运行自动扫描脚本
python scripts/discover.py

# 脚本会自动：
# 1. 扫描项目结构
# 2. 检查代码质量
# 3. 分析测试覆盖
# 4. 检查安全问题
# 5. 生成 memory/backlog.md 报告
```

### 方式二：手动执行

在 `self-loop` 开始前自动调用，生成待办清单供用户选择。

## 集成说明

- 与 `self-test` 集成：获取最新覆盖率数据
- 与 `self-loop` 集成：作为循环的发现阶段
- 与 `memory/backlog.md` 集成：持久化待办事项
- 支持增量扫描：只扫描上次以来变更的文件

## 使用示例

```bash
# 完整扫描
/self-discover

# 只扫描测试覆盖
/self-discover --focus=tests

# 只扫描安全问题
/self-discover --focus=security

# 扫描特定目录
/self-discover --path=backend/services
```
