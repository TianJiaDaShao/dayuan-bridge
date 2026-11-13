圆桥 Dayuan Bridge 0.2.1 Preview

这是独立开发的本地连接服务，不属于腾讯或 Apple 官方产品。
当前安装包为本地构建，未使用 Developer ID 签名或 Apple 公证。

安装后
  后台服务通过 launchd 自动启动，不再按30分钟会话授权。
  打开企业微信并登录，保留一个大圆会话；窗口可以最小化。
  当前兼容 Apple silicon、企微5.0.13（70807）及匹配的Xcode命令行工具。

使用
  dayuan status
  dayuan ask '查询项目问题清单末条记录及附件图片' --timeout 600
  dayuan ask '你的只读任务' --output result.txt
  dayuan submit '你的只读任务'
  dayuan result 任务ID --wait 20

管理
  dayuan service stop
  dayuan service start
  dayuan service restart
  dayuan service uninstall
  停止本次运行后，下次系统启动仍会运行。卸载才会移除自启动配置。
  启动、重启及卸载通过系统sudo进行管理员验证，不保存密码。
  卸载保留本机任务历史，不修改或删除企微文档。

任务
  一次跟踪一个任务，超时后轮询同一个任务ID，不要盲目重发。
  任务完成前不要切换大圆会话。服务重启后会恢复任务跟踪，不自动重发。
  如需放弃跟踪，明确运行 dayuan forget 任务ID；远端任务可能仍在执行。
  本机最多保留200条已结束任务及当前任务，目录仅管理员可直接读取。
  当前通过只读指令约束任务；这不是底层权限隔离。

目录
  程序：/Library/Application Support/Dayuan Bridge
  服务：/Library/LaunchDaemons/local.dayuan.bridge.plist
  任务：/var/db/dayuan-bridge/当前用户UID/jobs.json
  本地连接：/var/run/dayuan-bridge/当前用户UID/bridge.sock
  元数据日志：/var/log/dayuan-bridge

边界
  连接服务在本机运行，但任务由企微大圆及其云端能力执行。
  不导出或保存Cookie、登录Token或管理员密码，不监听网络端口。
  不修改sudoers、不关闭SIP，也不扩大企微账号的文档访问权限。
  其他企微版本会拒绝调用，需先验证兼容性。
