# packages/server/examples/01_core_workflow.py
"""
示例 1：核心工作流

本示例展示了最基础的端到端流程：
1. 提交翻译请求 (TM 未命中，创建 DRAFT)。
2. 手动模拟一个成功的翻译结果 (创建 REVIEWED 修订)。
3. 发布该修订。
4. 获取已发布的最终结果。
5. 添加并查看评论。
"""
import asyncio

from _shared import example_runner, logger


async def main() -> None:
    """执行核心工作流示例。"""
    async with example_runner("th_example_01.db") as coordinator:
        project_id = "demo-app"
        namespace = "onboarding.v1"
        keys = {"screen": "welcome", "element": "title"}
        source_payload = {"text": "Welcome to the App!"}
        
        logger.info("🚀 步骤 1: 提交翻译请求 (目标: de)...")
        content_id = await coordinator.request_translation(
            project_id=project_id, namespace=namespace, keys=keys,
            source_payload=source_payload, target_langs=["de"]
        )
        head = await coordinator.handler.get_translation_head_by_uida(
            project_id=project_id, namespace=namespace, keys=keys, target_lang="de", variant_key="-"
        )
        assert head is not None and head.current_status == "draft"
        logger.info("✅ 请求成功，任务进入 'DRAFT' 状态。", head_id=head.id)

        logger.info("👷 步骤 2: 模拟 Worker 处理并成功翻译...")
        # 真实场景中，Worker 会调用翻译引擎。这里我们直接创建 'reviewed' 修订。
        reviewed_rev_id = await coordinator.handler.create_new_translation_revision(
            head_id=head.id, project_id=project_id, content_id=content_id,
            target_lang="de", variant_key="-", status="reviewed",
            revision_no=head.current_no + 1,
            translated_payload_json={"text": "Willkommen in der App!"},
            engine_name="debug"
        )
        logger.info("✅ 模拟处理完成，新修订进入 'REVIEWED' 状态。", rev_id=reviewed_rev_id)
        
        logger.info("📢 步骤 3: 发布该 'reviewed' 修订...")
        success = await coordinator.publish_translation(reviewed_rev_id)
        assert success is True
        logger.info("✅ 修订已成功发布！")

        logger.info("🔍 步骤 4: 客户端获取已发布的翻译...")
        translation = await coordinator.get_translation(
            project_id=project_id, namespace=namespace, keys=keys, target_lang="de"
        )
        assert translation is not None and translation["text"] == "Willkommen in der App!"
        logger.info("🎉 成功获取翻译", result=translation)

        logger.info("💬 步骤 5: 添加并查看评论...")
        await coordinator.add_comment(head.id, "product_manager", "Looks good!")
        comments = await coordinator.get_comments(head.id)
        assert len(comments) == 1
        logger.info("🎉 成功添加并获取评论", author=comments[0].author, body=comments[0].body)


if __name__ == "__main__":
    asyncio.run(main())