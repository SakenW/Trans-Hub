# Guide 1: Quick Start

**Goal**: This guide will take you through the entire process from installing `Trans-Hub` to running your first asynchronous translation task in 5 minutes, allowing you to personally experience its powerful intelligent caching feature.

**Prerequisite**: You have installed Python 3.9 or higher.

---

### **步骤 1：安装 Trans-Hub**

安装 `Trans-Hub` 及其默认的 `translators` 引擎。

```bash
pip install "trans-hub[translators]"
```

### **步骤 2：运行基础用法示例**

我们已经为您准备好了一个功能完善的入门脚本。它将向您展示 `Trans-Hub` 的核心工作流：初始化、登记任务、执行翻译，并通过模拟第二次运行来演示持久化缓存。

1.  **找到示例文件**:
    在项目的 `examples/` 目录中，找到 `01_basic_usage.py` 文件。

2.  **阅读代码**:
    打开文件并阅读其中的注释，它详细解释了每一步的作用。

3.  **运行脚本**:
    在您的终端中，从项目根目录执行以下命令：
    ```bash
    poetry run python examples/01_basic_usage.py
    ```

观察日志输出，您将看到脚本在一次运行中就演示了首次翻译和缓存命中两种情况。

---

### **Congratulations!**

You have successfully run your first `Trans-Hub` translation task.

Where to go next?

- Ready to explore more powerful features? Please continue reading the **[Advanced Usage Guide](./02_advanced_usage.md)**.
- Want to see how `Trans-Hub` performs in a real concurrent environment? Please run our **[Real World Simulation Example](../examples/02_real_world_simulation.py)**.