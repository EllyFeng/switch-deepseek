# DeepSeek 切换脚本（最小版）详细规格说明

> 本文档已经吸收“目标字段定稿说明”的最终结论。
> 仅凭本文件 +《DeepSeek 切换脚本-技术文档》两份文档，应该能够完成实现。
> 本文档不讨论代码实现细节，只定义脚本的输入、输出、行为、边界、最终字段策略与判定规则。

---

## 1. 文档目的

本说明用于把“最小版 PRD”进一步收敛为一份可直接指导实现的脚本规格。

目标是回答下面这些问题：

- 脚本叫什么
- 接受哪些命令
- 操作哪些文件
- 允许修改哪些字段
- 默认保留哪些字段
- 如何判断当前状态
- 哪些情况必须报错退出
- 哪些情况只提示但继续执行

本文档仍然坚持最小范围，不扩展成功能设计文档或技术架构文档。

---

## 2. 产物定义

本版本只交付一个脚本文件。

### 2.1 产物形态

- 单个脚本文件
- 本地命令行执行
- 不依赖数据库
- 不依赖常驻服务
- 不依赖前端页面

### 2.2 暂定名称

建议脚本名：

`switch-deepseek.sh`

说明：

- 名称直接表达用途
- 明确这是 shell 脚本而不是应用程序
- 后续如改成其他脚本语言，可再调整名称，但本阶段先按 shell 脚本命名

---

## 3. 运行对象与作用范围

### 3.1 唯一作用对象

脚本唯一面向：

- 本机 Claude Code 用户配置

### 3.2 唯一主操作文件

脚本的主操作文件固定为：

- `~/.claude/settings.json`

### 3.3 允许读取但默认不修改的周边对象

脚本可以感知但不应主动修改：

- `~/.claude/`
- `~/.claude.json`
- `~/.claude/*` 其他文件

特别说明：

- `~/.claude.json` 不在本版本修改范围内
- 本版本不处理 MCP、onboarding、插件缓存、状态栏缓存

---

## 4. 脚本命令定义

本版本只支持 3 个一级命令。

### 4.1 `status`

用途：

- 查看当前状态
- 不产生任何写操作

标准形式：

```bash
./switch-deepseek.sh status
```

### 4.2 `switch`

用途：

- 将当前 Claude Code 接入配置切换到预设 DeepSeek 接入配置

标准形式：

```bash
./switch-deepseek.sh switch
```

### 4.3 `restore`

用途：

- 将当前配置恢复到首次切换前备份的原始 Claude 配置

标准形式：

```bash
./switch-deepseek.sh restore
```

---

## 5. 不支持的命令范围

本版本明确不支持以下命令或模式：

- `list`
- `add-provider`
- `remove-provider`
- `switch codex`
- `switch gemini`
- `switch openrouter`
- `backup list`
- `rollback <version>`
- `doctor`
- `migrate`
- `init`
- 交互式菜单模式

原因：

- 这些能力都会把脚本从“最小切换器”膨胀成“配置平台”

---

## 6. 固定文件路径约定

### 6.1 主配置文件

- `~/.claude/settings.json`

### 6.2 备份文件

建议固定为：

- `~/.claude/settings.json.deepseek-switch.backup`

选择固定单备份文件，而不是时间戳多版本，原因是：

- 最小版本只需要保留一份原始配置
- 降低状态复杂度
- 降低用户理解成本

### 6.3 临时写入文件

脚本在写入时可以使用临时文件，例如：

- `~/.claude/settings.json.tmp.<timestamp>`

但这是实现细节，不对用户暴露为正式接口。

---

## 7. DeepSeek 目标配置来源

本版本不支持用户通过命令行动态输入任意 provider 模板。

### 7.1 目标配置来源原则

脚本内部应内置一份“预设 DeepSeek 接入配置规则”。

这份规则不是完整 `settings.json` 模板，而是一组**字段级 patch 规则**。

### 7.2 为什么不能用整份模板

原因如下：

1. 用户本地 `settings.json` 不是空白文件
2. 其中大量内容与模型切换无关
3. 模板替换会造成不必要破坏

因此，本版本只允许：

- 用 patch 改字段
- 不用模板覆盖整文件

---

## 8. patch 字段白名单

本版本只允许修改下列字段。

### 8.1 一级修改范围

脚本仅允许修改：

- 顶层 `env` 对象中的特定键

### 8.2 第一版最终 patch 集合

第一版真正允许写入的字段，最终定稿为：

- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- 一个目标认证字段：
  - `env.ANTHROPIC_AUTH_TOKEN`，或
  - `env.ANTHROPIC_API_KEY`

说明：

- 认证字段只选择一种作为预设主字段写入
- 另一种字段默认保留原样，不主动清空，除非后续另行立项明确要求

### 8.3 第一版明确不写入的字段

以下字段在第一版中**不新增、不覆盖、不删除**：

- `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `env.ANTHROPIC_DEFAULT_SONNET_MODEL`
- `env.ANTHROPIC_DEFAULT_OPUS_MODEL`
- 顶层 `model`

### 8.4 DeepSeek 目标值来源规则

以下两个值必须来自脚本内部预设常量，而不是运行时动态输入：

- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`

实现要求：

- 在真正写代码前，必须先把这两个预设常量定成唯一明确值
- 本版本不支持命令行传入任意 URL 或任意模型名

---

## 9. patch 字段保留名单

本版本默认必须保留以下内容，不得因切换而重建或清空。

### 9.1 顶层保留字段

包括但不限于：

- `statusLine`
- `hooks`
- `permissions`
- `plugins`
- `theme`
- `outputStyle`
- `includeCoAuthoredBy`
- `cleanupPeriodDays`
- `env` 里与 provider 无关的其他键

### 9.2 保留原则

如果现有 `settings.json` 中存在下列任一非目标字段：

- 脚本必须原样保留
- 不得因切换丢失
- 不得因 restore 之外的流程覆盖掉

---

## 10. `status` 命令规格

### 10.1 输入

```bash
./switch-deepseek.sh status
```

不接受额外参数。

### 10.2 输出目标

至少输出以下信息：

1. 主配置文件路径
2. 主配置文件是否存在
3. 备份文件路径
4. 备份文件是否存在
5. 当前状态判定
6. 当前关键字段摘要

### 10.3 当前状态判定枚举

`status` 只输出以下三类之一：

- `claude-like`
- `deepseek-like`
- `unknown`

### 10.4 `claude-like` 判定规则

当满足以下任一组合时，可判定为 `claude-like`：

- `ANTHROPIC_MODEL` 明显仍是 Claude 模型命名
- 或 `ANTHROPIC_DEFAULT_*` 多数仍为 Claude 命名
- 且 `BASE_URL` 不明显指向 DeepSeek 目标入口

说明：

- 这是弱判定，不要求 100% 正确
- 只作为状态提示，不作为阻止执行的硬门槛

### 10.5 `deepseek-like` 判定规则

当以下条件中的大部分成立时，可判定为 `deepseek-like`：

- `ANTHROPIC_BASE_URL` 等于预设 DeepSeek 入口
- `ANTHROPIC_MODEL` 等于预设 DeepSeek 模型名
- 目标认证字段已设置

### 10.6 `unknown` 判定规则

如果无法稳定归入前两类，则输出 `unknown`。

典型情况包括：

- 用户已接入其他自定义网关
- 部分字段像 Claude，部分字段像 DeepSeek
- 关键字段缺失

### 10.7 字段摘要展示规则

`status` 应展示：

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_MODEL`
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `ANTHROPIC_DEFAULT_SONNET_MODEL`
- `ANTHROPIC_DEFAULT_OPUS_MODEL`
- `ANTHROPIC_AUTH_TOKEN` 是否存在
- `ANTHROPIC_API_KEY` 是否存在
- 顶层 `model` 的当前值（若存在）

敏感字段展示要求：

- token / key 不输出明文
- 只显示“已设置 / 未设置”

---

## 11. `switch` 命令规格

### 11.1 输入

```bash
./switch-deepseek.sh switch
```

不接受额外参数。

### 11.2 前置检查

执行 `switch` 前必须检查：

1. `~/.claude/settings.json` 是否存在
2. 文件是否可读
3. 文件内容是否为合法 JSON 对象

任一失败则直接退出，不得继续切换。

### 11.3 备份策略

执行 `switch` 时：

- 如果备份文件不存在：创建备份
- 如果备份文件已存在：默认保留，不覆盖

### 11.4 备份创建要求

备份内容必须是：

- 切换前完整的原始 `settings.json`

不是：

- 只备份 `env`
- 只备份差异字段
- 只备份 provider 段

### 11.5 patch 行为

切换时应：

1. 读取当前完整 JSON
2. 确保顶层存在 `env` 对象；若不存在则创建空对象
3. 只更新白名单字段
4. 保留其他内容不变
5. 将结果安全写回原文件

### 11.6 对 `env` 不存在时的处理

如果原始配置没有 `env`：

- 允许自动创建 `env: {}`
- 然后写入 DeepSeek 所需键

### 11.7 对 `env` 不是对象时的处理

如果顶层 `env` 存在，但不是 JSON 对象：

- 视为非法配置
- 直接报错退出
- 不进行切换

### 11.8 默认模型字段处理原则

以下字段在第一版中的最终规则已经定稿：

- `ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `ANTHROPIC_DEFAULT_SONNET_MODEL`
- `ANTHROPIC_DEFAULT_OPUS_MODEL`

最终规则：

- 如果原配置里没有这 3 个键，`switch` 不新增
- 如果原配置里有这 3 个键，`switch` 也不改写
- `restore` 时仍由完整备份恢复

选择这一规则的原因：

- 最小副作用
- 当前本机配置里本来没有这 3 个键
- 第一版目标是改“当前主接入”，不是重建完整模型家族映射
- 更利于回滚与排障

### 11.9 顶层 `model` 处理原则

第一版最终规则已经定稿：

- 默认保留原值
- 不主动删除
- 不主动改写

原因：

- 当前无法证明顶层 `model` 必然必须切换
- 贸然修改可能带来额外兼容问题
- 当前本机配置里已存在 `model: "opus"`，保留原值更稳妥

---

## 12. `restore` 命令规格

### 12.1 输入

```bash
./switch-deepseek.sh restore
```

不接受额外参数。

### 12.2 前置检查

执行 `restore` 前必须检查：

1. 备份文件是否存在
2. 备份文件是否可读
3. 备份内容是否为合法 JSON 对象

任一失败则直接退出。

### 12.3 恢复策略

恢复时：

- 使用备份文件完整覆盖 `~/.claude/settings.json`
- 不进行字段级 merge
- 不根据当前状态做智能恢复

### 12.4 恢复成功标准

恢复完成后：

- `settings.json` 应与备份内容一致
- 非 provider 字段应完全回到备份时状态

---

## 13. 文件写入安全策略

### 13.1 写入原则

所有会修改配置的命令都必须：

- 先生成新内容
- 再通过临时文件写入
- 最后再替换正式文件

### 13.2 禁止的写入方式

禁止：

- 直接边读边改原文件
- 用不安全的文本替换修改 JSON
- 用正则粗暴替换字段字符串

原因：

- 这类做法容易破坏 JSON 结构
- 容易留下半写状态

---

## 14. 失败场景与退出规则

### 14.1 必须报错退出的场景

以下情况发生时，脚本必须退出并返回失败状态：

1. 主配置文件不存在（对 `switch` 而言）
2. 主配置文件不可读
3. 主配置文件不是合法 JSON
4. 主配置文件根节点不是对象
5. `env` 存在但不是对象
6. 创建备份失败
7. 写入临时文件失败
8. 替换正式文件失败
9. `restore` 时备份不存在
10. `restore` 时备份 JSON 非法

### 14.2 可以告警但继续的场景

以下情况可以提示但继续：

1. 当前状态判定为 `unknown`
2. 已存在备份文件，因此本次不再重复备份
3. 当前看起来已经是 `deepseek-like`，但仍允许再次执行 `switch`

---

## 15. 幂等性要求

### 15.1 `status`

- 必须天然幂等
- 多次执行结果仅随当前文件状态变化

### 15.2 `switch`

- 在相同目标配置下重复执行，不应继续破坏其他字段
- 若已是目标 DeepSeek 配置，重复执行后结果应保持稳定

### 15.3 `restore`

- 多次执行 `restore`，只要备份有效，结果都应稳定

---

## 16. 日志与输出规范

### 16.1 输出风格

输出必须：

- 简洁
- 明确
- 可直接让用户判断下一步

### 16.2 成功输出至少应说明

- 做了什么
- 操作了哪个文件
- 备份是否创建或复用
- 当前结果状态

### 16.3 失败输出至少应说明

- 哪一步失败
- 哪个文件失败
- 为什么失败

### 16.4 不输出的内容

不得输出：

- token 明文
- API key 明文
- 大段 JSON 原文

---

## 17. 环境依赖约束

本版本应尽量减少依赖。

### 17.1 推荐依赖

允许依赖：

- `jq`
- shell 基础命令

### 17.2 不建议引入

不建议为了这个最小版本引入：

- Python 项目结构
- Node 项目结构
- Rust 二进制
- 第三方配置框架

原因：

- 会让“一个脚本”的目标失真

---

## 18. 实现前必须先定死的常量

在真正写代码之前，开发者必须先给出以下 3 个唯一明确值：

1. 预设 DeepSeek 兼容入口：
   - 用于写入 `env.ANTHROPIC_BASE_URL`
2. 预设 DeepSeek 目标模型名：
   - 用于写入 `env.ANTHROPIC_MODEL`
3. 目标认证字段与其值来源：
   - 使用 `env.ANTHROPIC_AUTH_TOKEN` 还是 `env.ANTHROPIC_API_KEY`
   - 以及该值来自哪里

说明：

- 这 3 项必须在实现前明确
- 一旦定下，第一版脚本不支持运行时动态传入任意 URL 或任意模型名
- 如果这 3 项没定，学员可以完成脚本框架，但不能完成可用版本

---

## 19. 向后兼容与范围控制

### 19.1 不承担历史兼容责任

本脚本不是通用迁移器，因此不承担：

- 兼容过去所有 Claude Code 配置格式
- 自动识别所有非标准配置
- 自动兼容所有第三方网关差异

### 19.2 本版本只保证最常见路径

只围绕下面这一路径优化：

- 用户已经有 `~/.claude/settings.json`
- 文件是标准 JSON 对象
- 用户希望改 `env` 中的 provider 相关字段

---

## 20. 一句话规格结论

这个脚本的详细规格应被严格理解为：

**一个只操作 `~/.claude/settings.json` 的单脚本工具，提供 `status / switch / restore` 三个命令；切换时只对白名单字段做 patch，首次切换前完整备份原始配置，恢复时只从备份完整还原，不扩展到多 provider、MCP、代理或 UI。**
