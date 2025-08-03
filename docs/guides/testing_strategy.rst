.. # docs/guides/testing_strategy.rst

==================
测试策略与指南
==================

`Trans-Hub` 项目致力于维护一个高质量、高覆盖率的测试套件。本指南详细介绍了项目的测试哲学、分层结构以及如何为新功能贡献测试。

测试哲学
--------

我们的测试遵循以下核心原则，这些原则与我们的 :doc:`../CONTRIBUTING` 指南一脉相承：

分层测试
  我们严格区分 :strong:`单元测试` 和 :strong:`集成测试`，以在测试速度和覆盖范围之间取得平衡。

行为驱动 (BDD)
  测试应验证一个组件的 :strong:`公共接口和外部行为` （输入与输出），而不是其内部实现细节。这使得重构内部代码时，测试用例依然有效。

确定性 (Deterministic)
  所有测试，特别是单元测试，都必须是确定性的。:strong:`严禁` 依赖物理时间（如 `sleep`）或随机性。所有不确定性因素（如网络、时间）都必须通过 `pytest-mock` 进行精确控制。

CI 优先
  所有代码在合并前，:strong:`必须` 在干净的 CI 环境中通过所有测试（`pytest`）、类型检查（`mypy`）和代码风格检查（`ruff`）。

测试分层结构
------------

项目的测试代码都位于 `tests/` 目录下，并被划分为两个主要部分：

`tests/unit/`
  - **职责**: 存放所有 :strong:`单元测试`。
  - **特点**:
    - :strong:`快速`: 每个测试都应在几毫秒内完成。
    - :strong:`隔离`: 只测试单个类或函数，其所有外部依赖（如其他类、数据库、网络）都 :strong:`必须` 被 `mocker` 模拟掉。
    - :strong:`无 I/O`: 单元测试 :strong:`绝不` 允许执行任何文件、网络或数据库 I/O 操作。

`tests/integration/`
  - **职责**: 存放所有 :strong:`集成测试` 和 :strong:`端到端 (E2E) 测试`。
  - **特点**:
    - :strong:`真实`: 测试多个组件的协同工作。
    - :strong:`允许 I/O`: 可以执行真实的数据库操作（通常是内存数据库或临时文件）和模拟的 CLI 调用。
    - :strong:`覆盖完整流程`: 用于验证从用户输入（如 CLI 命令）到系统最终状态（如数据库记录）的完整工作流。

运行测试
--------

我们使用 `pytest` 作为测试运行器。

.. code-block:: shell
   :caption: 运行所有测试

   poetry run pytest

.. code-block:: shell
   :caption: 只运行快速的单元测试 (在 CI 中用于快速反馈)

   poetry run pytest tests/unit/

.. code-block:: shell
   :caption: 运行特定文件的测试

   poetry run pytest tests/integration/cli/test_cli_request.py

测试 Fixtures (`conftest.py`)
-----------------------------

我们利用 `pytest` 的 Fixture 机制来管理测试依赖和环境。

`tests/unit/`
  此目录下的测试通常直接使用 `pytest-mock` 提供的 `mocker` fixture 来创建 mock 对象。

`tests/integration/cli/conftest.py`
  提供用于测试 CLI 命令 :strong:`行为` 的 Fixtures。核心 Fixture 包括：

  `cli_runner`
    提供一个 `CliRunner` 实例来模拟命令行调用。

  `mock_cli_backend`
    一个 :strong:`非自动` 的 fixture，当被测试函数请求时，它会 :strong:`完全 mock 掉` `Coordinator` 和数据库，允许我们只测试 CLI 的参数解析、流程控制和输出是否正确，而无需执行真实的业务逻辑。

`tests/integration/conftest.py`
  提供用于 :strong:`端到端测试` 的、:strong:`真实` 的组件实例。核心 Fixture 包括：

  `test_config`
    为每个测试创建一个指向全新临时数据库的 `TransHubConfig`。

  `coordinator`
    一个 :strong:`完全可用` 的、连接到真实（临时）数据库的 `Coordinator` 实例。这是进行端到端流程验证的关键。

如何贡献测试
------------

当您贡献一个新功能或修复一个 Bug 时，请遵循以下步骤：

1.  **确定测试类型**:
    - 如果您修改的是一个独立的、无依赖或依赖可被轻松 mock 的工具函数，请在 `tests/unit/` 下为其添加单元测试。
    - 如果您添加了一个新的 CLI 命令或修改了 `Coordinator` 的核心流程，请在 `tests/integration/` 下为其添加集成测试。
2.  **编写测试用例**:
    - 遵循“安排 (Arrange) -> 行动 (Act) -> 断言 (Assert)”的模式。
    - 使用 `mocker` 或我们提供的 `conftest.py` Fixtures 来准备测试环境。
    - 调用您要测试的函数或 CLI 命令。
    - 断言其返回值、最终状态或副作用（例如，一个 mock 是否被以正确的参数调用）是否符合预期。
3.  **运行本地检查**: 在提交前，请务必在本地运行完整的 CI 检查流程：

    .. code-block:: shell

       poetry run ruff format .
       poetry run ruff check --fix
       poetry run mypy .
       poetry run pytest