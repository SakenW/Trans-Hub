<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details open>
<summary><strong>English</strong></summary>

**English** | [简体中文](../../zh/root_files/ROADMAP.md)

### **Trans-Hub Unified Development Roadmap (v2.2 Final Version)**

**Current Status**: The **first phase of the core library: Performance and Core Optimization** has been fully completed (the `v3.0.0` milestone has been achieved). The codebase quality is stable, the architecture is clear, performance has been optimized, and it has passed 100% of all quality gates. We are now standing on a solid foundation, ready to build features upward.

**Overall Goal**: To gradually evolve Trans-Hub from a powerful **core library** into a **flexible, easy-to-use tool**, ultimately becoming a **deployable, observable production-grade service**.

### **Phase One: Performance and Core Optimization - [✅ Completed]**

#### **🎯 Goal**

Complete performance optimization of the core library to ensure its performance in high-concurrency scenarios.

#### **✅ [Completed] Task 1.1: Optimize Database Write Performance**

*   **Results**: The `ensure_pending_translations` method in `persistence.py` has been refactored to utilize the `INSERT ... ON CONFLICT` (UPSERT) syntax, significantly improving write performance and atomicity.

### **Phase Two: Tooling & Observability - [🚀 Current Stage]**

#### **🎯 Goal**

Package the core library into a fully functional command-line tool with a good user experience, and establish a complete observability system to achieve the project's first "implementation.

#### **⏳ [To Do] Task 2.1: Build Command Line Interface (CLI)**

*   **Subtask 2.1.1**: **Create CLI Module and Dependency Assembly**
    *   **Action**: Create `trans_hub/cli/main.py`, import `typer`. Create a `_setup_coordinator()` helper function responsible for all dependencies' "manual DI" process.
*   **Subtask 2.1.2**: **Implement Core CLI Commands**
    *   **Action**: Create core commands such as `request`, `process`, `gc`, and consider using the `rich` library to provide clear, formatted output.
*   **Subtask 2.1.3**: **Implement DLQ Management Commands**
    *   **Action**: Add methods like `replay_from_dlq`, `count_dlq`, `clear_dlq` in `Coordinator` and `PersistenceHandler`. Create subcommands like `dlq replay` and `dlq show` in the CLI.
*   **Deliverable**: A fully functional, user-friendly operational tool that can be directly used with the `trans-hub` command.

#### **⏳ [To-Do] Task 2.2: Establish Observability (Metrics)**

*   **Subtask 2.2.1**: **Define the `MetricsRecorder` interface and implementation**
    *   **Action**: Define the `MetricsRecorder` protocol in `interfaces.py`. Create `trans_hub/metrics.py` and implement `PrometheusMetricsRecorder` and `NoOpMetricsRecorder`.
*   **Subtask 2.2.2**: **Apply metrics using the decorator pattern**
    *   **Action**: Create `MetricsPolicyDecorator` in `policies.py`, which wraps a real `ProcessingPolicy` instance and records key metrics (such as processing count, time taken, cache hit rate, etc.) before and after the `process_batch` call.
*   **Subtask 2.2.3**: **Assemble at the CLI entry point**
    *   **Action**: In the `_setup_coordinator` function, decide based on the configuration whether to use `PrometheusMetricsRecorder` or `NoOpMetricsRecorder` to wrap `DefaultProcessingPolicy`.
*   **Deliverable**: A fully decoupled, pluggable monitoring system that lays the foundation for performance monitoring and alerting.

#### **⏳ [To Do] Task 2.3: Improve Configuration and Logging**

*   **Subtask 2.3.1**: **Enhance the runtime configuration capability of logs**
    *   **Action**: Add `--log-level` and `--log-format` options to the CLI, allowing users to override default configurations at runtime, greatly improving the convenience of debugging and operations.
*   **Deliverable**: An application with more flexible and easier-to-debug logging behavior.

### **Phase Three: Servitization & Deployment**

#### **🎯 Goal**

Expose the capabilities of Trans-Hub through the network, making it a deployable, easily configurable, and monitorable microservice.

#### **⏳ [To Do] Task 3.1: Package as Web API Service**

*   **Subtask 3.1.1**: **Create server module with FastAPI dependency injection**
    *   **Action**: Create `trans_hub/server/main.py`. Rewrite the logic of `_setup_coordinator` using FastAPI's `Depends` mechanism to achieve request-level dependency injection and application lifecycle management.
*   **Subtask 3.1.2**: **Implement API endpoints**
    *   **Action**: Create RESTful API routes corresponding to CLI functions such as `POST /request`, `POST /process-jobs`, `GET /metrics`, etc.
*   **Subtask 3.1.3**: **Containerization**
    *   **Action**: Write a `Dockerfile` to package the application into an image and provide a `docker-compose.yml` for one-click local service startup.
*   **Deliverable**: A fully service-oriented, deployable, and monitorable instance of Trans-Hub.

### **Phase Four: Ecosystem & Community**

#### **🎯 Goal**

Transform Trans-Hub into an open-source project with a good ecosystem, easy to expand and contribute to.

#### **⏳ [Future] Task 4.1: Establish a Plugin-Based Engine System**

*   **Action**: Explore expanding the engine discovery mechanism from "in-package discovery" to support dynamically loading third-party engine packages through `entry_points`, allowing the community to easily develop and share custom engines.

#### **⏳ [Future] Task 4.2: Improve Developer and User Documentation**

*   **Action**: Create a formal documentation website (such as using `MkDocs` or `Sphinx`), providing detailed architecture descriptions, API references, contribution guidelines, and usage tutorials.

</details>

<details>
<summary><strong>简体中文</strong></summary>

**English** | [简体中文](../../zh/root_files/ROADMAP.md)

### **Trans-Hub Unified Development Roadmap (v2.2 Final Version)**

**Current Status**: The **first phase of the core library: Performance and Core Optimization** has been fully completed (the `v3.0.0` milestone has been achieved). The codebase quality is stable, the architecture is clear, performance has been optimized, and it has passed 100% of all quality gates. We are now standing on a solid foundation, ready to build features upward.

**Overall Goal**: To gradually evolve Trans-Hub from a powerful **core library** into a **flexible, easy-to-use tool**, ultimately becoming a **deployable, observable production-grade service**.

### **Phase One: Performance and Core Optimization - [✅ Completed]**

#### **🎯 Goal**

Complete performance optimization of the core library to ensure its performance in high-concurrency scenarios.

#### **✅ [Completed] Task 1.1: Optimize Database Write Performance**

*   **Results**: The `ensure_pending_translations` method in `persistence.py` has been refactored to utilize the `INSERT ... ON CONFLICT` (UPSERT) syntax, significantly improving write performance and atomicity.

### **Phase Two: Tooling & Observability - [🚀 Current Stage]**

#### **🎯 Goal**

Package the core library into a fully functional command-line tool with a good user experience, and establish a complete observability system to achieve the project's first "implementation.

#### **⏳ [To Do] Task 2.1: Build Command Line Interface (CLI)**

*   **Subtask 2.1.1**: **Create CLI Module and Dependency Assembly**
    *   **Action**: Create `trans_hub/cli/main.py`, import `typer`. Create a `_setup_coordinator()` helper function responsible for all dependencies' "manual DI" process.
*   **Subtask 2.1.2**: **Implement Core CLI Commands**
    *   **Action**: Create core commands such as `request`, `process`, `gc`, and consider using the `rich` library to provide clear, formatted output.
*   **Subtask 2.1.3**: **Implement DLQ Management Commands**
    *   **Action**: Add methods like `replay_from_dlq`, `count_dlq`, `clear_dlq` in `Coordinator` and `PersistenceHandler`. Create subcommands like `dlq replay` and `dlq show` in the CLI.
*   **Deliverable**: A fully functional, user-friendly operational tool that can be directly used with the `trans-hub` command.

#### **⏳ [To-Do] Task 2.2: Establish Observability (Metrics)**

*   **Subtask 2.2.1**: **Define the `MetricsRecorder` interface and implementation**
    *   **Action**: Define the `MetricsRecorder` protocol in `interfaces.py`. Create `trans_hub/metrics.py` and implement `PrometheusMetricsRecorder` and `NoOpMetricsRecorder`.
*   **Subtask 2.2.2**: **Apply metrics using the decorator pattern**
    *   **Action**: Create `MetricsPolicyDecorator` in `policies.py`, which wraps a real `ProcessingPolicy` instance and records key metrics (such as processing count, time taken, cache hit rate, etc.) before and after the `process_batch` call.
*   **Subtask 2.2.3**: **Assemble at the CLI entry point**
    *   **Action**: In the `_setup_coordinator` function, decide based on the configuration whether to use `PrometheusMetricsRecorder` or `NoOpMetricsRecorder` to wrap `DefaultProcessingPolicy`.
*   **Deliverable**: A fully decoupled, pluggable monitoring system that lays the foundation for performance monitoring and alerting.

#### **⏳ [To Do] Task 2.3: Improve Configuration and Logging**

*   **Subtask 2.3.1**: **Enhance the runtime configuration capability of logs**
    *   **Action**: Add `--log-level` and `--log-format` options to the CLI, allowing users to override default configurations at runtime, greatly improving the convenience of debugging and operations.
*   **Deliverable**: An application with more flexible and easier-to-debug logging behavior.

### **Phase Three: Servitization & Deployment**

#### **🎯 Goal**

Expose the capabilities of Trans-Hub through the network, making it a deployable, easily configurable, and monitorable microservice.

#### **⏳ [To Do] Task 3.1: Package as Web API Service**

*   **Subtask 3.1.1**: **Create server module with FastAPI dependency injection**
    *   **Action**: Create `trans_hub/server/main.py`. Rewrite the logic of `_setup_coordinator` using FastAPI's `Depends` mechanism to achieve request-level dependency injection and application lifecycle management.
*   **Subtask 3.1.2**: **Implement API endpoints**
    *   **Action**: Create RESTful API routes corresponding to CLI functions such as `POST /request`, `POST /process-jobs`, `GET /metrics`, etc.
*   **Subtask 3.1.3**: **Containerization**
    *   **Action**: Write a `Dockerfile` to package the application into an image and provide a `docker-compose.yml` for one-click local service startup.
*   **Deliverable**: A fully service-oriented, deployable, and monitorable instance of Trans-Hub.

### **Phase Four: Ecosystem & Community**

#### **🎯 Goal**

Transform Trans-Hub into an open-source project with a good ecosystem, easy to expand and contribute to.

#### **⏳ [Future] Task 4.1: Establish a Plugin-Based Engine System**

*   **Action**: Explore expanding the engine discovery mechanism from "in-package discovery" to support dynamically loading third-party engine packages through `entry_points`, allowing the community to easily develop and share custom engines.

#### **⏳ [Future] Task 4.2: Improve Developer and User Documentation**

*   **Action**: Create a formal documentation website (such as using `MkDocs` or `Sphinx`), providing detailed architecture descriptions, API references, contribution guidelines, and usage tutorials.

</details>
