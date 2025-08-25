# packages/server/examples/04_collaboration_workflow.py
"""
示例 4：协作翻译工作流

本示例展示了多人协作翻译的完整流程：
1. 项目管理和任务分配
2. 译者协作和进度跟踪
3. 审校流程和质量控制
4. 评论和反馈系统
5. 版本管理和冲突解决

适用于大型翻译项目的团队协作场景。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict

from _shared import example_runner, print_section_header, print_step, print_success

# 模拟团队成员
TEAM_MEMBERS = {
    "translator_zh": {
        "name": "张译者",
        "role": "translator",
        "languages": ["zh-CN"],
        "specialization": "技术文档",
    },
    "translator_ja": {
        "name": "田中翻訳者",
        "role": "translator",
        "languages": ["ja-JP"],
        "specialization": "用户界面",
    },
    "reviewer_zh": {
        "name": "李审校",
        "role": "reviewer",
        "languages": ["zh-CN"],
        "specialization": "质量控制",
    },
    "project_manager": {
        "name": "王经理",
        "role": "manager",
        "languages": ["zh-CN", "ja-JP", "en-US"],
        "specialization": "项目管理",
    },
}

# 模拟翻译任务
TRANSLATION_TASKS = [
    {
        "id": "task_001",
        "content": "User authentication and authorization system",
        "namespace": "docs.security",
        "priority": "high",
        "deadline": datetime.now() + timedelta(days=2),
        "assigned_to": "translator_zh",
        "target_lang": "zh-CN",
    },
    {
        "id": "task_002",
        "content": "Database connection configuration",
        "namespace": "docs.database",
        "priority": "medium",
        "deadline": datetime.now() + timedelta(days=3),
        "assigned_to": "translator_zh",
        "target_lang": "zh-CN",
    },
    {
        "id": "task_003",
        "content": "Login",
        "namespace": "ui.auth",
        "priority": "high",
        "deadline": datetime.now() + timedelta(days=1),
        "assigned_to": "translator_ja",
        "target_lang": "ja-JP",
    },
    {
        "id": "task_004",
        "content": "Settings",
        "namespace": "ui.navigation",
        "priority": "low",
        "deadline": datetime.now() + timedelta(days=5),
        "assigned_to": "translator_ja",
        "target_lang": "ja-JP",
    },
]


async def setup_collaboration_project(coordinator, project_id: str) -> None:
    """
    设置协作翻译项目。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID
    """
    print_step(1, "设置协作翻译项目")

    # 在实际实现中，这里会调用：
    # await coordinator.create_project(
    #     project_id=project_id,
    #     name="多语言产品文档",
    #     description="产品文档和UI的多语言本地化项目",
    #     source_lang="en-US",
    #     target_langs=["zh-CN", "ja-JP"],
    #     workflow_type="collaborative"
    # )

    # 添加团队成员
    for user_id, member_info in TEAM_MEMBERS.items():
        # await coordinator.add_project_member(
        #     project_id=project_id,
        #     user_id=user_id,
        #     role=member_info["role"],
        #     permissions=get_role_permissions(member_info["role"])
        # )
        pass

    print_success(
        "协作项目设置完成", team_members=len(TEAM_MEMBERS), target_languages=2
    )


async def assign_translation_tasks(coordinator, project_id: str) -> Dict[str, str]:
    """
    分配翻译任务。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID

    Returns:
        Dict[str, str]: 任务ID到内容ID的映射
    """
    print_step(2, "分配翻译任务")

    task_content_mapping = {}

    for task in TRANSLATION_TASKS:
        # 提交翻译请求
        keys = {"section": task["namespace"], "task_id": task["id"]}
        source_payload = {"text": task["content"]}

        content_id = await coordinator.request_translation(
            project_id=project_id,
            namespace=task["namespace"],
            keys=keys,
            source_payload=source_payload,
            target_langs=[task["target_lang"]],
        )

        # 在实际实现中，这里会调用：
        # await coordinator.assign_task(
        #     content_id=content_id,
        #     assignee=task["assigned_to"],
        #     priority=task["priority"],
        #     deadline=task["deadline"]
        # )

        task_content_mapping[task["id"]] = content_id

    print_success("任务分配完成", tasks_assigned=len(TRANSLATION_TASKS))
    return task_content_mapping


async def simulate_translation_work(
    coordinator, task_mapping: Dict[str, str]
) -> Dict[str, str]:
    """
    模拟译者工作过程。

    Args:
        coordinator: 协调器实例
        task_mapping: 任务到内容ID的映射

    Returns:
        Dict[str, str]: 内容ID到修订版本ID的映射
    """
    print_step(3, "模拟译者翻译工作")

    # 模拟翻译结果
    translation_results = {
        "task_001": "用户身份验证和授权系统",
        "task_002": "数据库连接配置",
        "task_003": "ログイン",
        "task_004": "設定",
    }

    revision_mapping = {}

    for task_id, content_id in task_mapping.items():
        task = next(t for t in TRANSLATION_TASKS if t["id"] == task_id)
        translator = TEAM_MEMBERS[task["assigned_to"]]

        print(f"   👤 {translator['name']} 正在翻译: {task['content']}")

        # 模拟翻译过程
        translated_text = translation_results[task_id]
        # target_payload = {"text": translated_text}

        # 在实际实现中，这里会调用：
        # revision_id = await coordinator.submit_translation(
        #     content_id=content_id,
        #     target_lang=task["target_lang"],
        #     target_payload=target_payload,
        #     translator_id=task["assigned_to"]
        # )

        revision_id = f"rev_{content_id}_{task['target_lang']}"
        revision_mapping[content_id] = revision_id

        print(f"   ✅ 翻译完成: {translated_text}")

    print_success("翻译工作完成", translations_submitted=len(task_mapping))
    return revision_mapping


async def simulate_review_process(
    coordinator, revision_mapping: Dict[str, str]
) -> Dict[str, bool]:
    """
    模拟审校流程。

    Args:
        coordinator: 协调器实例
        revision_mapping: 内容ID到修订版本ID的映射

    Returns:
        Dict[str, bool]: 审校结果
    """
    print_step(4, "模拟审校流程")

    review_results = {}
    reviewer = TEAM_MEMBERS["reviewer_zh"]

    print(f"   👤 {reviewer['name']} 开始审校中文翻译")

    for content_id, revision_id in revision_mapping.items():
        # 只审校中文翻译
        if "zh-CN" in revision_id:
            # 模拟审校决定（大部分通过）
            import random

            approved = random.choice([True, True, True, False])  # 75%通过率

            if approved:
                # await coordinator.approve_translation(
                #     revision_id=revision_id,
                #     reviewer_id="reviewer_zh",
                #     comments="翻译质量良好，术语使用准确。"
                # )
                print(f"   ✅ 审校通过: {revision_id}")
            else:
                # await coordinator.request_revision(
                #     revision_id=revision_id,
                #     reviewer_id="reviewer_zh",
                #     comments="建议调整术语表达，使其更符合技术文档规范。"
                # )
                print(f"   🔄 需要修订: {revision_id}")

            review_results[revision_id] = approved
        else:
            # 日文翻译暂时跳过审校
            review_results[revision_id] = True
            print(f"   ⏭️  日文翻译暂时跳过审校: {revision_id}")

    approved_count = sum(review_results.values())
    print_success(
        "审校流程完成",
        total_reviewed=len(review_results),
        approved=approved_count,
        needs_revision=len(review_results) - approved_count,
    )

    return review_results


async def simulate_feedback_system(
    coordinator, revision_mapping: Dict[str, str]
) -> None:
    """
    模拟评论和反馈系统。

    Args:
        coordinator: 协调器实例
        revision_mapping: 修订版本映射
    """
    print_step(5, "模拟评论和反馈系统")

    # 模拟各种类型的评论
    sample_comments = [
        {
            "author": "reviewer_zh",
            "type": "suggestion",
            "content": "建议将'用户身份验证'改为'用户认证'，更符合行业惯例。",
        },
        {
            "author": "translator_zh",
            "type": "response",
            "content": "感谢建议，我会在下个版本中修改。",
        },
        {
            "author": "project_manager",
            "type": "approval",
            "content": "整体翻译质量很好，符合项目要求。",
        },
    ]

    for comment in sample_comments:
        author_name = TEAM_MEMBERS[comment["author"]]["name"]
        print(f"   💬 {author_name} ({comment['type']}): {comment['content']}")

        # 在实际实现中，这里会调用：
        # await coordinator.add_comment(
        #     revision_id=list(revision_mapping.values())[0],
        #     author_id=comment["author"],
        #     content=comment["content"],
        #     comment_type=comment["type"]
        # )

    print_success("反馈系统演示完成", comments_added=len(sample_comments))


async def track_project_progress(coordinator, project_id: str) -> None:
    """
    跟踪项目进度。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID
    """
    print_step(6, "跟踪项目进度")

    # 模拟进度统计
    progress_stats = {
        "total_tasks": len(TRANSLATION_TASKS),
        "completed_tasks": 3,
        "in_review_tasks": 1,
        "pending_tasks": 0,
        "overall_progress": 0.75,
    }

    print("\n📊 项目进度概览:")
    print(f"   • 总任务数: {progress_stats['total_tasks']}")
    print(f"   • 已完成: {progress_stats['completed_tasks']}")
    print(f"   • 审校中: {progress_stats['in_review_tasks']}")
    print(f"   • 待处理: {progress_stats['pending_tasks']}")
    print(f"   • 整体进度: {progress_stats['overall_progress']:.1%}")

    # 团队工作量统计
    print("\n👥 团队工作量:")
    for user_id, member in TEAM_MEMBERS.items():
        if member["role"] == "translator":
            assigned_tasks = [
                t for t in TRANSLATION_TASKS if t["assigned_to"] == user_id
            ]
            print(f"   • {member['name']}: {len(assigned_tasks)} 个任务")

    print_success(
        "进度跟踪完成", overall_progress=f"{progress_stats['overall_progress']:.1%}"
    )


async def demonstrate_version_control(coordinator) -> None:
    """
    演示版本管理功能。

    Args:
        coordinator: 协调器实例
    """
    print_step(7, "演示版本管理")

    # 模拟版本历史
    version_history = [
        {
            "version": "v1.0",
            "author": "translator_zh",
            "timestamp": datetime.now() - timedelta(hours=2),
            "changes": "初始翻译",
        },
        {
            "version": "v1.1",
            "author": "reviewer_zh",
            "timestamp": datetime.now() - timedelta(hours=1),
            "changes": "审校修订：调整术语表达",
        },
        {
            "version": "v1.2",
            "author": "translator_zh",
            "timestamp": datetime.now(),
            "changes": "根据反馈进行最终调整",
        },
    ]

    print("\n📚 版本历史:")
    for version in version_history:
        author_name = TEAM_MEMBERS[version["author"]]["name"]
        timestamp = version["timestamp"].strftime("%H:%M")
        print(
            f"   • {version['version']} - {author_name} ({timestamp}): {version['changes']}"
        )

    print_success("版本管理演示完成", total_versions=len(version_history))


async def generate_collaboration_report(coordinator, project_id: str) -> None:
    """
    生成协作报告。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID
    """
    print_section_header("协作项目报告", "📋")

    print("🎯 项目概览:")
    print(f"   • 项目ID: {project_id}")
    print(f"   • 团队规模: {len(TEAM_MEMBERS)} 人")
    print("   • 目标语言: zh-CN, ja-JP")
    print(f"   • 任务总数: {len(TRANSLATION_TASKS)}")

    print("\n👥 团队贡献:")
    for user_id, member in TEAM_MEMBERS.items():
        role_desc = {"translator": "译者", "reviewer": "审校", "manager": "经理"}[
            member["role"]
        ]
        print(f"   • {member['name']} ({role_desc}): {member['specialization']}")

    print("\n⏱️  时间统计:")
    print("   • 平均翻译时间: 30分钟/任务")
    print("   • 平均审校时间: 15分钟/任务")
    print("   • 项目总耗时: 3小时")

    print("\n🎉 质量指标:")
    print("   • 一次通过率: 75%")
    print("   • 平均修订次数: 1.2次")
    print("   • 客户满意度: 95%")


async def main() -> None:
    """执行协作翻译工作流示例。"""
    print_section_header("协作翻译工作流演示", "🤝")

    async with example_runner("collaboration.db") as coordinator:
        project_id = "collaborative-docs"

        # 设置协作项目
        await setup_collaboration_project(coordinator, project_id)

        # 分配翻译任务
        task_mapping = await assign_translation_tasks(coordinator, project_id)

        # 模拟翻译工作
        revision_mapping = await simulate_translation_work(coordinator, task_mapping)

        # 模拟审校流程
        await simulate_review_process(coordinator, revision_mapping)

        # 模拟反馈系统
        await simulate_feedback_system(coordinator, revision_mapping)

        # 跟踪项目进度
        await track_project_progress(coordinator, project_id)

        # 演示版本管理
        await demonstrate_version_control(coordinator)

        # 生成协作报告
        await generate_collaboration_report(coordinator, project_id)

        print_section_header("协作工作流完成", "🎉")
        print("\n🔗 下一步: 运行 05_quality_assurance.py 查看质量保证示例")


if __name__ == "__main__":
    asyncio.run(main())
