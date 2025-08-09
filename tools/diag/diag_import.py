# tools/diag/diag_import.py
import sys
from pathlib import Path

# --- 确保项目根目录在 sys.path 中 ---
try:
    # 脚本在 tools/diag/，根目录是上上级
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(f"✅ 项目根目录已添加: {project_root}")
except Exception as e:
    print(f"⚠️ 无法自动添加项目根目录: {e}")
# ---

print("\n--- 诊断脚本开始 ---")
try:
    print("正在尝试导入 'rfc8785'...")
    import rfc8785
    print("✅ 成功导入 rfc8785")
    print(f"   - 路径: {rfc8785.__file__}")
    print(f"   - 函数: {rfc8785.dumps}")

except ImportError as e:
    print(f"\n❌ 导入失败: {e}")
    print("\n这是一个严重的环境问题。请确认您已严格执行了环境净化指令。")
    print("\n当前 sys.path:")
    for p in sys.path:
        print(f"  - {p}")

print("\n--- 诊断脚本结束 ---")