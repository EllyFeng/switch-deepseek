# DeepSeek 切换脚本技术文档

> 本文档基于以下材料综合整理：
>
> - `cc-switch` 相关源码阅读结论
> - 本机现有脚本范例 `~/.claude/scripts/switch-statusline.sh`
> - 当前本机 Claude Code 配置 `~/.claude/settings.json`
> - 《DeepSeek 切换脚本-详细规格说明》中的最终实现边界
>
> 目标是：在真正写代码之前，把全局上下文、影响点、技术边界与处理方案一次性梳理清楚。

---

## 1. 文档目标

本文档不是 PRD，也不是逐字段规格抄录，而是一份**面向实现前决策**的技术文档。

它要回答 4 个问题：

1. 这个脚本到底是在改什么
2. 当前本机与参考项目里有哪些真实影响点
3. 为什么方案必须收敛成现在这样
4. 实现时哪些地方可以借鉴，哪些地方绝对不能照搬

---

## 2. 结论先行

最小版 DeepSeek 切换脚本的本质不是：

**“把 Claude Code 原生切成 DeepSeek”**

而是：

**“把 Claude Code 当前使用的接入配置，切换成一个预设的 DeepSeek 兼容入口配置，并保留完整回滚能力。”**

因此，这个脚本的职责边界必须严格限定为：

- 只操作 `~/.claude/settings.json`
- 只提供 `status / switch / restore`
- 只做字段级 patch
- 只保留一份原始备份
- 不引入 provider 管理体系
- 不触碰 `~/.claude.json`
- 不接管 MCP、代理、状态栏、插件或数据库

---

## 3. 全局上下文梳理

### 3.1 当前工作目录的性质

当前目录 `/Users/diaoye/Desktop/ccdoctor` 不是某个单一应用仓库，而是这次需求的工作区。

当前与本任务直接相关的内容分成两部分：

1. 本机真实 Claude Code 配置：
   - `~/.claude/settings.json`
   - `~/.claude/scripts/switch-statusline.sh`

2. 参考实现：
   - `/Users/diaoye/Desktop/ccdoctor/cc-switch`

### 3.2 为什么必须同时看“本机配置”和“参考项目”

只看 `cc-switch`，容易做成一个过重的多 provider 系统。  
只看本机 `settings.json`，又容易低估配置联动和写入安全问题。

所以本次技术方案必须同时建立在：

- **`cc-switch` 给出的正确方向**
- **你当前本机环境给出的真实约束**

这也是为什么前面一直强调“先通读相关代码，梳理全局上下文，定位所有影响点”。

---

## 4. 本机真实配置上下文

### 4.1 当前主配置文件

当前 Claude Code 主配置文件是：

- `~/.claude/settings.json`

这与 `cc-switch` 中的 Claude live config 结论一致：

- 参考代码：`cc-switch/src-tauri/src/config.rs:73`
- `get_claude_settings_path()` 默认返回 `~/.claude/settings.json`

### 4.2 当前配置中的关键事实

从当前 `~/.claude/settings.json` 看，和本任务相关的事实有：

1. 顶层存在：
   - `model: "opus"`
2. 顶层存在：
   - `statusLine.command`
3. 顶层存在：
   - `hooks`
   - `permissions`
   - `enabledPlugins`
4. `env` 当前只包含：
   - `HTTP_PROXY`
   - `HTTPS_PROXY`
   - `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`
5. 当前 `env` **没有**：
   - `ANTHROPIC_BASE_URL`
   - `ANTHROPIC_AUTH_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `ANTHROPIC_MODEL`
   - `ANTHROPIC_DEFAULT_*`

### 4.3 这些事实带来的真实约束

这意味着：

- 不能覆盖整个 `env`，否则会丢失代理配置
- 不能覆盖整个 `settings.json`，否则会丢失 hooks / statusLine / enabledPlugins
- 不能把脚本设计成“假设用户已有完整 Anthropic provider 配置”
- 第一版切换时很可能需要**新建** `env.ANTHROPIC_*` 相关键

---

## 5. 本机现有脚本范例带来的启发

本机已有脚本：

- `~/.claude/scripts/switch-statusline.sh`

这个脚本虽然不是模型切换脚本，但它提供了一个很贴近你使用习惯的本地范式。

### 5.1 可借鉴的地方

1. **单脚本形态**
   - 没有项目骨架
   - 没有数据库
   - 没有 UI

2. **固定入口命令**
   - 通过简单命令参数驱动行为

3. **切换前先备份**
   - 有明确的 `backup_settings()` 思路

4. **状态查询独立存在**
   - 有 `status` 概念

### 5.2 不能照搬的地方

它里面也有几处不适合作为本次脚本的实现方式：

1. 它通过 `grep` 判断状态
   - 对 JSON 配置来说太脆弱

2. 它存在 `sed` 兜底修改 JSON 的逻辑
   - 对本次任务不合适
   - 容易破坏 JSON

3. 它直接用 `cp` 备份、`mv` 替换
   - 思路可参考，但 DeepSeek 脚本应更强调 JSON 合法性与原子写入意识

因此，`switch-statusline.sh` 更适合作为：

- 交互风格参考
- 用户体验参考
- 最小脚本形态参考

而**不适合作为 JSON patch 实现方式参考**。

---

## 6. `cc-switch` 源码中与本任务真正相关的部分

前面已经通读并定位过相关源码，这里只保留实现决策最需要的结论。

### 6.1 Claude live config 的真实落点

`cc-switch` 对 Claude 的 live config 落点是：

- `~/.claude/settings.json`

关键代码：

- `cc-switch/src-tauri/src/config.rs:73`
- `cc-switch/src-tauri/src/services/provider/live.rs:695`

这个结论非常关键，因为它证明：

- Claude 切换的主战场不是数据库
- 不是多个碎片文件
- 更不是 UI 状态
- 就是 `settings.json`

### 6.2 `cc-switch` 对 Claude 的写入本质

Claude 分支写入本质是：

1. 取得 provider 的 `settings_config`
2. 做 sanitize
3. 写回 `settings.json`

关键代码：

- `cc-switch/src-tauri/src/services/provider/live.rs:26`
- `cc-switch/src-tauri/src/services/provider/live.rs:697`

这说明 `cc-switch` 的抽象核心是：

**provider = 一份可写回 live config 的配置对象**

### 6.3 `cc-switch` 的写入安全策略

`cc-switch` 使用：

- JSON 解析
- pretty serialize
- 原子写入

关键代码：

- `cc-switch/src-tauri/src/config.rs:181`
- `cc-switch/src-tauri/src/config.rs:203`

这说明最小版脚本虽然不需要 Rust 实现，但必须继承同样的写入原则：

- 不能直接字符串替换 JSON
- 不能用 grep/sed 粗暴写值
- 必须先构造合法 JSON，再安全落盘

### 6.4 `cc-switch` 的复杂能力为什么不该照搬

`cc-switch` 还包含：

- provider 数据库
- current provider 状态
- common config snippet
- backfill 到旧 provider
- MCP 同步
- proxy takeover / hot-switch
- 多应用支持（Claude/Codex/Gemini/...）

这些能力对桌面应用有价值，但对本次最小脚本是明显过度设计。

如果照搬，会出现 3 个问题：

1. 复杂度暴增
2. 风险边界扩大
3. 与“只做一个脚本”的需求冲突

因此，这些部分应全部视为：

- 研究背景
- 思路来源
- 明确排除项

而不是实现清单。

---

## 7. 已定位出的全部关键影响点

下面是这次方案涉及的真实影响点列表。

### 7.1 文件影响点

#### 必改文件

- `~/.claude/settings.json`

#### 只读文件

- `~/.claude/settings.json.deepseek-switch.backup`（若存在则用于 restore）
- `~/.claude/scripts/switch-statusline.sh`（仅作为风格参考）
- `cc-switch/src-tauri/src/config.rs`
- `cc-switch/src-tauri/src/services/provider/live.rs`
- `cc-switch/src-tauri/src/services/provider/mod.rs`

#### 明确不改文件

- `~/.claude.json`
- `~/.claude/plugins/**`
- `~/.claude/CLAUDE.md`
- `~/.claude/keybindings.json`

### 7.2 配置字段影响点

#### 必改字段

- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- 一个目标认证字段：
  - `env.ANTHROPIC_AUTH_TOKEN` 或
  - `env.ANTHROPIC_API_KEY`

#### 明确保留字段

- 顶层 `model`
- `statusLine`
- `hooks`
- `permissions`
- `enabledPlugins`
- `env.HTTP_PROXY`
- `env.HTTPS_PROXY`
- `env.CLAUDE_CODE_DISABLE_TERMINAL_TITLE`
- 其他非 provider 相关字段

#### 明确不动字段

- `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `env.ANTHROPIC_DEFAULT_SONNET_MODEL`
- `env.ANTHROPIC_DEFAULT_OPUS_MODEL`

### 7.3 行为影响点

#### `status` 的影响点

- 只能读，不写
- 要判断当前状态是否更像 Claude / DeepSeek / unknown
- 要脱敏展示认证字段存在性

#### `switch` 的影响点

- 需要首次完整备份
- 需要 patch 指定字段
- 需要保证原有 JSON 结构不被破坏

#### `restore` 的影响点

- 只能用原始备份完整覆盖恢复
- 不允许做智能 merge

### 7.4 用户环境影响点

- 当前用户环境存在代理配置
- 当前状态栏会读取 `ANTHROPIC_*`
- 当前插件体系已启用，不应受脚本影响

---

## 8. 技术边界与风险边界

### 8.1 这个脚本能解决什么

它能解决的是：

- 为 Claude Code 写入一套 DeepSeek 兼容接入字段
- 在失败时恢复到切换前的原始配置
- 尽量减少对用户其他配置的破坏

### 8.2 这个脚本不能解决什么

它不能保证：

- DeepSeek 兼容入口一定可用
- Claude Code 在该入口上完整支持 tool use / thinking / streaming
- 所有状态栏或插件都能正确理解新 provider
- 底层响应协议和 Anthropic 行为完全等价

### 8.3 为什么这个边界必须在技术文档里写清楚

因为如果不写清楚，后续实现很容易被误解成：

- 在做“模型迁移平台”
- 在做“Claude Code 官方 DeepSeek 支持”
- 在做“全链路无损替换”

而这三件事都不是当前需求。

---

## 9. 谨慎、完整的处理方案

下面给出最终建议方案。

### 9.1 方案总览

采用：

**单脚本 + 单配置文件 + 单备份文件 + 字段级 patch + 完整 restore**

不采用：

- 多 provider
- DB 状态存储
- 模板覆盖整文件
- MCP 联动
- 运行时动态选择 provider

### 9.2 命令层方案

只保留 3 个命令：

1. `status`
2. `switch`
3. `restore`

这样做的理由：

- 认知成本最低
- 与需求完全对齐
- 不给未来扩张留下模糊口子

### 9.3 文件层方案

#### 主文件

- `~/.claude/settings.json`

#### 备份文件

- `~/.claude/settings.json.deepseek-switch.backup`

#### 临时文件

- `~/.claude/settings.json.tmp.<timestamp>`

这样做的理由：

- 文件路径单一
- 恢复路径清晰
- 排障路径明确

### 9.4 patch 层方案

`switch` 时只改：

- `env.ANTHROPIC_BASE_URL`
- `env.ANTHROPIC_MODEL`
- 一个目标认证字段

不改：

- 顶层 `model`
- `ANTHROPIC_DEFAULT_*`
- `statusLine`
- `hooks`
- `permissions`
- `enabledPlugins`
- 代理字段

这样做的理由：

- 修改面最小
- 副作用最小
- 回滚最简单
- 最符合当前本机真实配置结构

### 9.5 备份与恢复方案

#### 备份

- 首次 `switch` 前完整备份当前 `settings.json`
- 后续 `switch` 默认不覆盖原始备份

#### 恢复

- `restore` 直接用备份完整覆盖 `settings.json`
- 不做智能 merge

这样做的理由：

- 原始备份最有价值
- 不会把错误状态再覆盖成“新备份”
- 恢复路径简单可靠

### 9.6 状态识别方案

`status` 输出三态：

- `claude-like`
- `deepseek-like`
- `unknown`

判定主要基于：

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_MODEL`
- 目标认证字段是否存在

这样做的理由：

- 足够提示用户
- 不需要复杂规则引擎
- 与最小版目标一致

### 9.7 写入安全方案

写入时必须采用：

1. 读取合法 JSON
2. 内存中构造 patch 后结果
3. 写入临时文件
4. 原子替换正式文件

这样做的理由：

- 继承 `cc-switch` 的安全思路
- 避免配置半写坏掉
- 避免 sed/grep 式误改

---

## 10. 为什么这是当前最优解

因为它同时满足了 5 件事：

1. **贴近 `cc-switch` 的正确核心**
   - live config
   - sanitize 思想
   - 原子写思路
   - 备份/恢复原则

2. **尊重你当前本机真实环境**
   - 保留代理
   - 保留状态栏
   - 保留 hooks / plugins

3. **符合“只实现一个脚本”的硬约束**
   - 不引入系统架构负担

4. **实现面足够小，适合先验证**
   - 有利于先跑通 MVP

5. **出问题时容易恢复**
   - 一份原始备份即可回到初始状态

---

## 11. 实现前最后仍需由用户提供的值

虽然技术策略已经收敛，但真正写脚本前，仍有 3 个具体值需要最终给定：

1. 预设 DeepSeek 兼容入口：
   - `ANTHROPIC_BASE_URL`
2. 预设 DeepSeek 目标模型名：
   - `ANTHROPIC_MODEL`
3. 目标认证字段与其值来源：
   - 使用 `ANTHROPIC_AUTH_TOKEN` 还是 `ANTHROPIC_API_KEY`

这是因为：

- 规则我们已经定完了
- 但生产值不能靠猜

---

## 12. 最终技术结论

这次需求的正确实现方向应被理解为：

**以 `~/.claude/settings.json` 为唯一 live config 落点，借鉴 `cc-switch` 的安全写入与回滚原则，但主动放弃其数据库、多 provider、MCP、代理接管等复杂体系；最终交付一个只支持 `status / switch / restore` 的单脚本工具，通过字段级 patch 把 Claude Code 当前接入切到预设 DeepSeek 兼容入口，并确保原始配置可以完整恢复。**
