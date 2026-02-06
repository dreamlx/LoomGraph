# language: zh-CN
@impact @p0
功能: 变更影响分析
  作为一个开发者
  我想知道我的代码变更会影响哪些模块
  以便我可以评估风险并通知相关人员

  背景:
    假如 LoomGraph 服务正常运行
    并且 代码库已经被索引

  @commit
  场景: 分析单个 commit 的影响
    假如 我刚提交了一个修改 "UserService.login" 的 commit
    当 我执行 "loomgraph impact HEAD"
    那么 我应该看到成功的 JSON 响应
    并且 响应包含 "changed_symbols" 列表
    并且 响应包含 "impact_analysis" 分析结果
    并且 "direct_callers" 包含调用了 "UserService.login" 的函数

  @staged
  场景: 分析暂存区变更的影响
    假如 我有修改 "PaymentService.process" 的暂存变更
    当 我执行 "loomgraph impact --staged"
    那么 我应该看到成功的 JSON 响应
    并且 响应包含暂存文件的影响分析

  @branch
  场景: 分析两个分支的差异影响
    假如 我在 "feature/auth-refactor" 分支
    并且 该分支相对于 "main" 有 5 个 commits
    当 我执行 "loomgraph impact main..HEAD"
    那么 我应该看到成功的 JSON 响应
    并且 响应包含所有变更符号的汇总
    并且 响应包含 "affected_modules" 列表

  @risk
  场景: 高风险变更的警告
    假如 我修改了被 10 个以上位置调用的核心函数
    当 我执行 "loomgraph impact HEAD"
    那么 "risk_assessment.level" 应该是 "high"
    并且 "risk_assessment.suggestions" 应该包含测试建议

  @file
  场景: 分析指定文件的变更影响
    假如 我修改了 "src/auth/validator.py"
    当 我执行 "loomgraph impact --file src/auth/validator.py"
    那么 我应该看到该文件中所有被修改符号的影响分析

  @error
  场景: 无变更时的处理
    假如 工作目录没有任何变更
    当 我执行 "loomgraph impact HEAD"
    那么 我应该看到提示 "No changes detected"

  @error
  场景: 无效 commit 的错误处理
    当 我执行 "loomgraph impact invalid-commit-hash"
    那么 我应该看到错误响应
    并且 错误码应该是 "INVALID_COMMIT"
