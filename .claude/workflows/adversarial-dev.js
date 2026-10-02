export const meta = {
  name: 'adversarial-dev',
  description: '开发 + 对抗性审查 + 修正循环（支持多需求顺序执行）',
  phases: [
    { title: 'Parse Requirements' },
    { title: 'Implement' },
    { title: 'Attack' },
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

if (requirements.length === 0) {
  throw new Error('请提供需求列表：\n' +
    '  - 分号分隔: "需求1; 需求2; 需求3"\n' +
    '  - 从文件读取: "@requirements.txt"')
}

log(`开始处理 ${requirements.length} 个需求`)

// 存储所有结果
const results = []

// 顺序处理每个需求
for (let i = 0; i < requirements.length; i++) {
  const requirement = requirements[i]
  const progress = `[${i + 1}/${requirements.length}]`

  log(`${progress} 开始: ${requirement}`)

  const result = {
    requirement,
    success: false,
    error: null,
  }

  try {
    // 阶段 1: 实现
    phase('Implement')
    await agent(
      `实现用户要求的功能：
       需求：${requirement}
       充分阅读相关文件，理解上下文，写出高质量实现
       添加测试覆盖正常和异常路径

       返回格式：{ description: "实现描述" }`,
      { label: `implement:${requirement}`, phase: 'Implement' }
    )

    // 阶段 2: 对抗性审查（多个 reviewer）
    phase('Attack')
    const reviewers = [
      () => agent(
        `你是一个严格的代码审查员。攻击性审查：
         需求：${requirement}
         审查维度：代码逻辑正确性
         检查：边界情况、异常路径、返回值正确性、状态一致性
         只报告真正的 bug，不要报告风格问题
         返回格式：{ issues: [{title, description, severity}] }`,
        { label: `attacker:logic:${requirement}`, phase: 'Attack' }
      ),
      () => agent(
        `你是一个测试专家。攻击性审查：
         需求：${requirement}
         审查维度：测试充分性
         检查：测试覆盖、边界测试、断言强度、Mock 使用
         只报告真正的测试缺陷，不要报告风格问题
         返回格式：{ issues: [{title, description, severity}] }`,
        { label: `attacker:tests:${requirement}`, phase: 'Attack' }
      ),
    ]

    const attacks = await parallel(reviewers)
    const issues = attacks.filter(Boolean).flatMap(a => a.issues || [])

    // 阶段 3: 修复
    if (issues.length > 0) {
      log(`${progress} 审查发现 ${issues.length} 个问题，正在修复...`)

      phase('Fix')
      await agent(
        `修复审查发现的问题：
         ${JSON.stringify(issues, null, 2)}
         逐一修复，添加测试，确保问题已解决
         运行测试验证修复`,
        { label: `fix:${requirement}`, phase: 'Fix' }
      )
    } else {
      log(`${progress} 审查通过，无需修复`)
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

return {
  total: results.length,
  success: successCount,
  failed: failCount,
  results,
}
