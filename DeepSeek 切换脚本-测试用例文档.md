# DeepSeek 切换脚本测试用例文档

## 1. 文档目标

本文档用于验证 `switch-deepseek.sh` 是否满足以下要求：

1. 符合既定规格，只操作 `~/.claude/settings.json`
2. 切换行为正确，只改白名单字段
3. 不破坏原有 Claude 配置中的其他关键字段
4. 能在首次切换前正确创建备份
5. 能从备份完整恢复原始配置
6. 在异常场景下安全失败，不留下半写状态
7. 切换到 DeepSeek 后具备基本可用性

本文档是测试方案与测试用例集合，不包含实现代码。

---

## 2. 测试范围

### 2.1 被测对象

- 脚本文件：`switch-deepseek.sh`

### 2.2 覆盖命令

- `status`
- `switch`
- `restore`

### 2.3 覆盖维度

- 功能正确性
- 配置保留正确性
- 备份与恢复能力
- 异常处理
- 幂等性
- 安全性
- 基本可用性

### 2.4 不在本轮测试范围内

- DeepSeek 服务端可用性 SLA
- Claude Code 对第三方 provider 的全部能力兼容性
- 插件内部逻辑正确性
- 网络代理本身是否可用

---

## 3. 测试环境要求

### 3.1 基础依赖

- macOS / Linux shell 环境
- `bash`
- `jq`
- 已安装 Claude Code
- 本机存在 `~/.claude/settings.json`

### 3.2 建议准备

为避免误伤真实配置，建议优先使用测试目录并通过环境变量覆盖：

- `CLAUDE_CONFIG_DIR=/path/to/test-claude-dir`

在测试目录中准备：

- `settings.json`
- 可选备份文件

### 3.3 测试数据建议

建议至少准备以下 4 类配置样本：

1. **标准 Claude 配置样本**
   - 含 `ANTHROPIC_MODEL`
   - 含 `ANTHROPIC_DEFAULT_*`
   - 含代理字段
   - 含 `statusLine` / `hooks` / `permissions` / `enabledPlugins`

2. **缺失 env 的样本**
   - 顶层有 `model`
   - 无 `env`

3. **非法 env 样本**
   - `env` 存在，但值不是对象

4. **已切换 DeepSeek 的样本**
   - `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL` 已是目标值

---

## 4. 核心判定标准

### 4.1 允许被修改的字段

切换后只允许变化：

- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- 一个目标认证字段：
  - `env.ANTHROPIC_AUTH_TOKEN` 或
  - `env.ANTHROPIC_API_KEY`

### 4.2 必须保留的字段

切换前后必须保持不变：

- 顶层 `model`
- `statusLine`
- `hooks`
- `permissions`
- `enabledPlugins`
- `env.HTTP_PROXY`
- `env.HTTPS_PROXY`
- `env.CLAUDE_CODE_DISABLE_TERMINAL_TITLE`
- `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `env.ANTHROPIC_DEFAULT_SONNET_MODEL`
- `env.ANTHROPIC_DEFAULT_OPUS_MODEL`
- 其他非目标字段

### 4.3 失败安全原则

如果发生异常，必须满足：

- 脚本返回失败状态
- `settings.json` 仍是合法 JSON
- 不出现截断、半写、空文件
- 不覆盖原始备份

---

## 5. 测试用例设计

---

### TC-001 `status` 在标准 Claude 配置上输出正确摘要

**目的**
验证 `status` 能正确读取标准 Claude 配置，并输出关键字段摘要。

**前置条件**
- `settings.json` 存在
- 根节点为合法 JSON 对象
- `env` 为对象
- 配置中含 Claude 相关字段

**执行步骤**
1. 运行：`bash switch-deepseek.sh status`
2. 观察输出

**预期结果**
- 返回成功状态
- 输出配置文件路径与备份文件路径
- 输出 `当前状态`
- 输出：
  - `ANTHROPIC_BASE_URL`
  - `ANTHROPIC_MODEL`
  - `ANTHROPIC_DEFAULT_*`
  - `ANTHROPIC_AUTH_TOKEN` 是否已设置
  - `ANTHROPIC_API_KEY` 是否已设置
  - 顶层 `model`
- 不输出 token / key 明文

---

### TC-002 `status` 在缺失 `env` 时可正常工作

**目的**
验证脚本可处理没有 `env` 的合法配置。

**前置条件**
- `settings.json` 存在
- 根节点为 JSON 对象
- 不包含 `env`

**执行步骤**
1. 运行：`bash switch-deepseek.sh status`

**预期结果**
- 返回成功状态
- 状态通常为 `unknown`
- 各个 `ANTHROPIC_*` 字段显示为空或未设置
- 不报错

---

### TC-003 `status` 在 `env` 非对象时应报错退出

**目的**
验证非法配置能被及时阻断。

**前置条件**
- `settings.json` 存在
- 根节点为 JSON 对象
- `env` 的值不是对象，例如字符串或数组

**执行步骤**
1. 运行：`bash switch-deepseek.sh status`

**预期结果**
- 返回失败状态
- 明确报错：`env` 存在但不是 JSON 对象
- 不修改任何文件

---

### TC-004 `switch` 首次执行时创建原始备份

**目的**
验证首次切换前会完整备份当前配置。

**前置条件**
- `settings.json` 存在且合法
- 备份文件不存在
- 脚本中的 DeepSeek 预设常量已填写真实值

**执行步骤**
1. 运行：`bash switch-deepseek.sh switch`
2. 检查备份文件是否创建
3. 对比备份内容与切换前原始 `settings.json`

**预期结果**
- 返回成功状态
- 生成 `settings.json.deepseek-switch.backup`
- 备份内容与切换前原始配置完全一致
- 备份不是仅保存 `env`，而是完整文件

---

### TC-005 `switch` 只修改白名单字段

**目的**
验证切换行为最小化，不扩大修改面。

**前置条件**
- `settings.json` 存在且合法
- 配置中存在多种非 provider 字段
- 备份文件可不存在

**执行步骤**
1. 记录切换前配置摘要
2. 运行：`bash switch-deepseek.sh switch`
3. 记录切换后配置摘要
4. 对比差异

**预期结果**
只有以下字段允许变化：
- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- 目标认证字段

其余字段保持不变，尤其是：
- `model`
- `statusLine`
- `hooks`
- `permissions`
- `enabledPlugins`
- `HTTP_PROXY`
- `HTTPS_PROXY`
- `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`
- `ANTHROPIC_DEFAULT_*`

---

### TC-006 `switch` 在缺失 `env` 时自动创建 `env`

**目的**
验证脚本可处理最小合法配置。

**前置条件**
- `settings.json` 合法
- 顶层无 `env`

**执行步骤**
1. 运行：`bash switch-deepseek.sh switch`
2. 检查输出文件

**预期结果**
- 返回成功状态
- 自动创建 `env: {}`
- 写入目标 DeepSeek 字段
- 其他顶层字段保持不变

---

### TC-007 `switch` 在 `env` 非对象时应报错退出

**目的**
验证脚本不会在非法配置上强行写入。

**前置条件**
- `settings.json` 合法
- `env` 存在但不是对象

**执行步骤**
1. 运行：`bash switch-deepseek.sh switch`

**预期结果**
- 返回失败状态
- 明确报错
- 不生成新配置
- 不破坏原文件

---

### TC-008 `switch` 在占位常量未填时应报错退出

**目的**
验证脚本不会带着假值改真实配置。

**前置条件**
- `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `TARGET_AUTH_VALUE` 至少一个仍是占位符

**执行步骤**
1. 运行：`bash switch-deepseek.sh switch`

**预期结果**
- 返回失败状态
- 报错指出哪个常量未填写
- 不应执行切换

---

### TC-009 `switch` 重复执行时结果稳定

**目的**
验证脚本具备幂等性。

**前置条件**
- 已完成一次成功切换
- 备份文件已存在

**执行步骤**
1. 再次运行：`bash switch-deepseek.sh switch`
2. 再次比较前后配置

**预期结果**
- 返回成功状态
- 提示复用已有备份
- 配置结果稳定
- 不重复覆盖原始备份
- 不新增无关字段

---

### TC-010 `restore` 可完整恢复原始配置

**目的**
验证切换后可回滚。

**前置条件**
- 已执行成功的 `switch`
- 备份文件存在且合法

**执行步骤**
1. 运行：`bash switch-deepseek.sh restore`
2. 对比当前 `settings.json` 与备份文件

**预期结果**
- 返回成功状态
- 当前 `settings.json` 与备份文件完全一致
- 切换前的 Claude 配置全部恢复
- 状态重新回到 `claude-like` 或与原始配置一致的状态

---

### TC-011 `restore` 在备份不存在时应报错退出

**目的**
验证恢复命令的前置检查。

**前置条件**
- 备份文件不存在

**执行步骤**
1. 运行：`bash switch-deepseek.sh restore`

**预期结果**
- 返回失败状态
- 明确提示找不到备份文件
- 不修改现有配置

---

### TC-012 `restore` 重复执行时结果稳定

**目的**
验证恢复幂等性。

**前置条件**
- 备份文件存在且合法
- 已执行过一次 `restore`

**执行步骤**
1. 再次运行：`bash switch-deepseek.sh restore`

**预期结果**
- 返回成功状态
- 当前配置保持稳定
- 不引入额外变化

---

### TC-013 `status` 在切换后正确识别为 `deepseek-like`

**目的**
验证状态识别规则正确。

**前置条件**
- 已成功执行 `switch`
- `ANTHROPIC_BASE_URL` 等于预设值
- `ANTHROPIC_MODEL` 等于预设值
- 目标认证字段已设置

**执行步骤**
1. 运行：`bash switch-deepseek.sh status`

**预期结果**
- 返回成功状态
- 输出 `当前状态: deepseek-like`

---

### TC-014 认证信息在 `status` 输出中必须脱敏

**目的**
验证敏感信息不会在状态查询中泄露。

**前置条件**
- 配置中存在 `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_API_KEY`

**执行步骤**
1. 运行：`bash switch-deepseek.sh status`
2. 检查终端输出

**预期结果**
- 仅显示 `已设置 / 未设置`
- 不出现 token / key 明文

---

### TC-015 配置写入后仍为合法 JSON

**目的**
验证写入安全性。

**前置条件**
- 存在合法 `settings.json`

**执行步骤**
1. 执行 `switch`
2. 使用 `jq` 校验写回后的 `settings.json`
3. 再执行 `restore`
4. 再次使用 `jq` 校验

**预期结果**
- `switch` 后配置是合法 JSON 对象
- `restore` 后配置仍是合法 JSON 对象
- 不出现截断文件或半写文件

---

### TC-016 切换后 Claude Code 基本可启动和读取配置

**目的**
验证切换后不是“只改字段但根本不可用”。

**前置条件**
- 已成功 `switch`
- 网络与 DeepSeek key 可用

**执行步骤**
1. 启动 Claude Code
2. 观察是否能正常读取配置
3. 尝试进行一次最小对话请求

**预期结果**
- Claude Code 能正常启动
- 不因配置格式损坏而报错
- 能发起一次基础请求
- 若请求失败，需区分是网络/API 问题还是配置结构问题

---

### TC-017 切换后状态栏相关配置未被破坏

**目的**
验证对现有 statusLine 兼容。

**前置条件**
- 原始配置包含 `statusLine.command`

**执行步骤**
1. 记录切换前 `statusLine`
2. 执行 `switch`
3. 对比 `statusLine`

**预期结果**
- `statusLine` 原样保留
- 不因切换而被删除或重建

---

### TC-018 切换后代理配置未被破坏

**目的**
验证现有代理设置被保留。

**前置条件**
- 原始配置中存在 `HTTP_PROXY` / `HTTPS_PROXY`

**执行步骤**
1. 记录代理字段
2. 执行 `switch`
3. 对比代理字段
4. 执行 `restore`
5. 再次对比

**预期结果**
- `switch` 后代理字段不变
- `restore` 后代理字段仍与原始配置一致

---

### TC-019 切换后默认模型映射字段未被改写

**目的**
验证第一版严格遵守“不碰 `ANTHROPIC_DEFAULT_*`”的边界。

**前置条件**
- 原始配置存在 `ANTHROPIC_DEFAULT_HAIKU_MODEL`
- 原始配置存在 `ANTHROPIC_DEFAULT_SONNET_MODEL`
- 原始配置存在 `ANTHROPIC_DEFAULT_OPUS_MODEL`

**执行步骤**
1. 记录这 3 个字段原值
2. 执行 `switch`
3. 检查这 3 个字段

**预期结果**
- 三个字段全部保持原值不变

---

### TC-020 顶层 `model` 在切换前后保持不变

**目的**
验证第一版严格遵守“不改顶层 `model`”的边界。

**前置条件**
- 原始配置存在顶层 `model`

**执行步骤**
1. 记录顶层 `model`
2. 执行 `switch`
3. 检查顶层 `model`
4. 执行 `restore`
5. 再次检查

**预期结果**
- `switch` 前后顶层 `model` 不变
- `restore` 后仍与原始值一致

---

## 6. 安全检查清单

除功能测试外，还应做如下安全检查：

### 6.1 明文密钥风险检查

检查项：
- 脚本是否把真实 API key 写死在文件里
- 终端输出是否泄露密钥
- 日志或截图中是否暴露密钥

期望：
- 生产脚本不应长期写死真实 key
- 状态输出不泄露明文

### 6.2 修改面检查

检查项：
- 是否修改了白名单外字段
- 是否动到了 `~/.claude.json`
- 是否影响插件、hooks、statusLine

期望：
- 第一版只改 `settings.json` 中白名单字段

### 6.3 恢复能力检查

检查项：
- 是否保留原始备份
- 重复切换时是否覆盖原始备份
- 恢复后是否真正回到初始状态

期望：
- 原始备份必须可用且不被二次覆盖

---

## 7. 推荐执行顺序

建议按以下顺序执行测试：

1. `TC-001` / `TC-002` / `TC-003` 先测 `status`
2. `TC-004` / `TC-005` / `TC-006` / `TC-007` / `TC-008` 测 `switch` 基本行为
3. `TC-009` 测 `switch` 幂等性
4. `TC-010` / `TC-011` / `TC-012` 测 `restore`
5. `TC-013` ~ `TC-020` 做完整性、安全性与可用性验证

---

## 8. 通过标准

只有当以下条件全部满足时，才能判定脚本“基本符合要求”：

1. 所有核心功能测试通过
2. 所有失败场景都能安全退出
3. 原始备份被正确创建且可用于恢复
4. `restore` 后配置与备份一致
5. 切换前后的非目标字段未被破坏
6. `status` 不泄露敏感信息
7. Claude Code 切换后至少具备基础可用性

---

## 9. 一句话结论模板

测试完成后，可按如下模板给出结论：

- **符合要求**：脚本满足最小版规格，切换、备份、恢复、状态识别和字段保留均符合预期。
- **部分符合要求**：核心功能可用，但仍存在若干安全性、幂等性或边界场景问题。
- **不符合要求**：脚本在关键路径上存在破坏配置、无法恢复或泄露敏感信息等问题。
