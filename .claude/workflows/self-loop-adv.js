export const meta = {
  name: 'self-loop-adv',
  description: 'Self-Loop 增强版：支持多需求顺序执行，集成对抗性验证的自动迭代开发',
  phases: [
    { title: 'Parse Requirements' },
    { title: 'Discover' },
    { title: 'Implement' },
    { title: 'Test' },
    { title: 'Adversarial Review' },
    { title: 'Fix' },
    { title: 'Commit' },
  ],
}

// 解析需求列表
function parseRequirements(input) {
  if (!input) return []

  // 从文件读取
  if (input.startsWith('@')) {
    const filePath = input.slice(1)
    try {
      const fs = require('fs')
      const content = fs.readFileSync(filePath, 'utf-8')
      return content
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'))
    } catch (e) {
      log(`读取文件失败: ${e.message}`)
      return []
    }
  }

  // 按分号分割
  return input
    .split(';')
    .map(s => s.trim())
    .filter(Boolean)
}

// 从 args 获取需求列表
const requirementsInput = args?.requirements || args?.[0] || ''
const requirements = parseRequirements(requirementsInput)

// 如果没有提供需求，使用自动发现模式
const useAutoDiscover = requirements.length === 0

log(`模式: ${useAutoDiscover ? '自动发现' : '多需求顺序执行'}`)
if (!useAutoDiscover) {
  log(`需求列表: ${requirements.join(', ')}`)
}

// 存储所有需求的处理结果
const results = []

if (useAutoDiscover) {
  // 自动发现模式：扫描项目，识别待处理问题
  phase('Discover')

  const issues = await agent(
    `扫描项目，识别待处理问题：
     1. 运行 python scripts/discover.py（如果存在）
     2. 读取 memory/backlog.md（如果存在）
     3. 按优先级排序：HIGH > MEDIUM > LOW
     4. 返回待处理问题列表
     返回格式：{ issues: [{title, description, priority}] }`,
    { label: 'discover', phase: 'Discover' }
  )

  const issueList = issues?.issues || []
  requirements.push(...issueList.map(i => i.title))
  log(`发现 ${requirements.length} 个待处理问题`)
}

// 顺序处理每个需求
for (let i = 0; i < requirements.length; i++) {
  const requirement = requirements[i]
  const progress = `[${i + 1}/${requirements.length}]`

  log(`${progress} 开始处理: ${requirement}`)

  const result = {
    requirement,
    success: false,
    error: null,
    files: [],
    testsPassed: 0,
  }

  try {
    // 阶段 1: 实现
    phase('Implement')
    const code = await agent(
      `实现以下需求：
       需求：${requirement}

       要求：
       1. 读取相关文件，理解上下文
       2. 分析现有代码模式，保持风格一致
       3. 编写实现代码
       4. 添加测试覆盖正常和异常路径
       5. 遵循项目规范（PEP8, type hints, 严格模式）

       返回格式：{ files: [{path, changes}], description: "变更描述" }`,
      { label: `implement:${requirement}`, phase: 'Implement' }
    )

    if (code?.files) {
      result.files = code.files.map(f => f.path)
    }

    // 阶段 2: 测试
    phase('Test')
    const testResult = await agent(
      `运行测试验证实现：
       1. 运行后端测试: python -m pytest backend/tests/ -v --cov=backend --tb=short
       2. 运行前端测试: cd frontend && npm test -- --watchAll=false（如果存在）
       3. 检查覆盖率是否 >= 80%
       4. 返回测试结果和覆盖率

       返回格式：{ passed: number, failed: number, coverage: number, errors: [string] }`,
      { label: `test:${requirement}`, phase: 'Test' }
    )

    result.testsPassed = testResult?.passed || 0

    // 如果测试失败，尝试修复
    if (testResult?.failed > 0) {
      log(`${progress} 测试失败，尝试修复...`)

      for (let fixAttempt = 1; fixAttempt <= 3; fixAttempt++) {
        phase('Fix')
        await agent(
          `修复测试失败：
           错误信息：${JSON.stringify(testResult.errors)}
           修复尝试：${fixAttempt}/3

           要求：
           1. 分析失败原因
           2. 修复代码或测试
           3. 重新运行失败的测试
           4. 确保覆盖率不下降`,
          { label: `fix:${requirement}:${fixAttempt}`, phase: 'Fix' }
        )

        // 重新运行测试
        const retestResult = await agent(
          `重新运行失败的测试：
           返回格式：{ passed: number, failed: number, coverage: number }`,
          { label: `retest:${requirement}:${fixAttempt}`, phase: 'Test' }
        )

        if (retestResult?.failed === 0) {
          log(`${progress} 修复成功`)
          break
        }

        if (fixAttempt === 3) {
          throw new Error(`3 次修复尝试后仍有 ${retestResult?.failed} 个测试失败`)
        }
      }
    }

    // 阶段 3: 对抗性审查
    phase('Adversarial Review')
    const reviews = await parallel([
      () => agent(
        `审查代码逻辑正确性：
         需求：${requirement}
         检查：边界情况、异常路径、返回值正确性、状态一致性
         返回格式：{ issues: [{title, description, severity}] }`,
        { label: `reviewer:logic:${requirement}`, phase: 'Adversarial Review' }
      ),
      () => agent(
        `审查测试充分性：
         需求：${requirement}
         检查：测试覆盖、边界测试、断言强度、Mock 使用
         返回格式：{ issues: [{title, description, severity}] }`,
        { label: `reviewer:tests:${requirement}`, phase: 'Adversarial Review' }
      ),
      () => agent(
        `审查安全和鲁棒性：
         需求：${requirement}
         检查：输入验证、错误处理、资源泄漏、并发安全
         返回格式：{ issues: [{title, description, severity}] }`,
        { label: `reviewer:security:${requirement}`, phase: 'Adversarial Review' }
      ),
    ])

    const reviewIssues = reviews.filter(Boolean).flatMap(r => r.issues || [])
    if (reviewIssues.length > 0) {
      log(`${progress} 审查发现 ${reviewIssues.length} 个问题，正在修复...`)

      phase('Fix')
      await agent(
        `修复审查发现的问题：
         ${JSON.stringify(reviewIssues, null, 2)}
         要求：逐一修复，添加测试，重新验证`,
        { label: `fix-review:${requirement}`, phase: 'Fix' }
      )
    }

    // 阶段 4: 提交
    phase('Commit')
    await agent(
      `提交代码变更：
       1. 暂存所有变更: git add -A
       2. 提交: git commit -m "feat: ${requirement}

Co-Authored-By: Claude Code <noreply@anthropic.com>"
       3. 返回提交哈希

       返回格式：{ commit: "哈希值" }`,
      { label: `commit:${requirement}`, phase: 'Commit' }
    )

    result.success = true
    log(`${progress} ✅ 完成: ${requirement}`)

  } catch (error) {
    result.error = error.message
    log(`${progress} ❌ 失败: ${requirement} - ${error.message}`)
  }

  results.push(result)
}

// 最终验证
phase('Final Validation')
await agent(
  `最终验证：
   1. 运行完整测试套件
   2. 检查覆盖率 >= 80%
   3. 确认所有变更已提交`,
  { label: 'final-validation', phase: 'Final Validation' }
)

// 生成执行报告
const successCount = results.filter(r => r.success).length
const failCount = results.length - successCount

log(`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 执行报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

总需求数: ${results.length}
成功: ${successCount}
失败: ${failCount}

详细结果:
${results.map((r, i) => {
  const status = r.success ? '✅' : '❌'
  return `${i + 1}. ${status} ${r.requirement}${r.error ? ` - ${r.error}` : ''}`
}).join('\n')}
`)

// 返回结果
return {
  total: results.length,
  success: successCount,
  failed: failCount,
  results,
}
