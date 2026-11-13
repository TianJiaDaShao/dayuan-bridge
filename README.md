# 圆桥 · Dayuan Bridge

将企业微信智能助理「大圆」接入本地 CLI。通过 Mac 上已有的登录态提交自然语言任务并取回结果，可用于查询文档、表格记录及附件图片，无需创建企业机器人。

**0.2.1 Preview · Apple silicon macOS · 企业微信 5.0.13（70807）**

独立开发项目，非腾讯或 Apple 官方产品。此工具依赖客户端内部接口与 LLDB 调试访问，不是企微官方开放 API；客户端升级或本机策略可能导致不可用。

## 当前验证范围

- 本地原型已完成真实任务提交、结果读取和附件图片识别，无需界面校准；企微窗口可以最小化。
- 服务版包含 launchd 安装、任务持久化、受限 Unix socket 和 CLI。相关逻辑有自动化测试。
- 安装包已完成构建与静态检查，**已在开发者 Mac 完成首次安装、自动拉起与真实文档查询验收；其他机器仍需验证**，仍属于实验预览版。
- 预览安装包未使用 Developer ID 签名，未经过 Apple 公证。需管理员安装权限、Xcode 命令行工具和可用的大圆会话；不会关闭 SIP 或修改 sudoers。

## 安装与使用

从 [Releases](https://github.com/TianJiaDaShao/dayuan-bridge/releases) 下载 `.pkg`，先核对同版本 `SHA256SUMS.txt`，再按安装向导操作。只在理解上述预览限制后安装；本仓库的发布不会自动在你的机器上安装服务。

保持企业微信登录，并打开一个可用的大圆会话：

```sh
dayuan status
dayuan ask '查询项目问题清单最新新增记录，说明时间依据并识别全部附件图片；只读，不修改文档。' --timeout 600
```

耗时任务可提交后轮询：

```sh
dayuan submit '查询指定文档并汇总结果，只读'
dayuan result <job_id> --wait 20
```

超时或返回未知状态后，继续轮询同一个任务 ID，不要盲目重复提交。任务执行期间保持当前大圆会话。结果只包含大圆实际返回的内容，不能保证每种文档、图片或云端工具都支持。

## AI 助手调用

AI 助手直接执行 CLI：先 `dayuan status`，再提交任务并按任务 ID 轮询。使用规则见 [docs/agent-rules.md](docs/agent-rules.md)。需由助手配置显式引用，下载仓库不会自动生效。

## 管理

```sh
dayuan service stop
dayuan service start
dayuan service restart
dayuan service uninstall
```

启动、重启和卸载可能要求本机管理员验证。停止服务不移除开机启动，卸载才移除。卸载保留本机任务历史。更多目录、保留策略及命令见 [运行说明](service/runtime/README.txt)。

## 数据与权限

服务不监听网络端口，不导出或保存 Cookie、登录 Token 或管理员密码。本地 Unix socket 按用户限制访问；服务需管理员权限访问客户端进程。任务与结果会保存在本机任务历史中，可能包含文档内容，请勿提交到公开仓库。

任务仍由大圆及其云端能力处理，不是离线运行。工具不扩大企微账号原有文档权限。当前以只读查询为目标，向大圆附加只读指令；**这不是底层写权限隔离**。

## 从源码构建

在兼容的 Mac 上安装 Xcode 命令行工具：

```sh
xcode-select --install
python3 -m unittest discover -s service/tests -p 'test_*.py' -v
python3 build_package.py
```

测试会编译独立的 Objective-C 测试程序，不需要操作真实企微。构建只生成文件，不安装或加载服务；产物在 `site/dist/downloads/`。

## 项目结构

- `service/runtime/`：本地桥接、CLI 和服务管理。
- `service/installer-scripts/`：安装前检查与安装配置。
- `service/tests/`：自动化测试与独立原生测试程序源码。
- `site/dist/`：可本地打开的产品介绍网页；下载链接需要对应的构建产物。
- `docs/agent-rules.md`：供本地 AI 助手采用的文档工具规则。

公开仓库不包含真实业务查询结果、文档附件、抓包、调试日志或本机凭据。发现问题请提交 Issue，避免附上敏感文档内容或登录信息。
