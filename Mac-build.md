# 推送到Mac端并自动编译

```bash
# 1. 进入 mac 目录
  cd E:\quick_model_mac

  # 2. 提交改动
  git add -A
  git commit -m "同步自动确认功能、流式显示修复、模型删除按钮"

  # 3. 推送到 mac 分支
  git push -u origin mac

  # 4. 打 tag 触发自动编译（GitHub Actions 监听 v* tag）
  git tag v1.5.1
  git push origin v1.5.1

  如果不想打 tag，也可以手动触发 workflow（因为你的 workflow 配了 workflow_dispatch）：

  gh workflow run build-mac.yml --ref mac

```
