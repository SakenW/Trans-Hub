# Guide 1: Quick Start

**Goal**: This guide will take you through the entire process from installing `Trans-Hub` to running your first asynchronous translation task in 5 minutes, allowing you to personally experience its powerful intelligent caching feature.

**Prerequisite**: You have installed Python 3.9 or higher.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

### **Step 1: Install Trans-Hub**

Install `Trans-Hub` and its default `translators` engine.

```bash
pip install "trans-hub[translators]"
```

### **Step 2: Run the Basic Usage Example**

We have prepared a fully functional introductory script for you. It will show you the core workflow of `Trans-Hub`: initialization, task registration, executing translations, and demonstrating persistent caching through a simulated second run.

1. **Find the example file**: In the project's `examples/` directory, locate the `01_basic_usage.py` file.

2. **Read the code**: Open the file and read the comments, which explain the function of each step in detail.

3.  **Run the script**:
    In your terminal, execute the following command from the project root directory:
    ```bash
    poetry run python examples/01_basic_usage.py
    ```

By observing the log output, you will see that the script demonstrates both the first translation and cache hit scenarios in a single run.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

### **Congratulations!**

You have successfully run your first `Trans-Hub` translation task.

Where to go next?

- Ready to explore more powerful features? Please continue reading the **[Advanced Usage Guide](./02_advanced_usage.md)**.
- Want to see how `Trans-Hub` performs in a real concurrent environment? Please run our **[Real World Simulation Example](../examples/02_real_world_simulation.py)**.