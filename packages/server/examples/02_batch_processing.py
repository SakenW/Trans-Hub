# packages/server/examples/02_batch_processing.py
"""
示例 2：批量翻译处理

本示例展示了如何批量处理多个翻译请求：
1. 批量提交多个翻译请求
2. 处理多种语言和内容类型
3. 模拟批量翻译处理
4. 批量发布和查询结果
5. 统计和报告功能

适用于大规模内容本地化场景。
"""

import asyncio
from typing import Dict, List
from _shared import example_runner, print_section_header, print_step, print_success


# 模拟电商平台的多语言内容
SAMPLE_CONTENT = {
    "product_titles": [
        "Premium Wireless Headphones",
        "Smart Fitness Watch",
        "Portable Power Bank 20000mAh",
        "Wireless Charging Pad",
        "Bluetooth Speaker"
    ],
    "product_descriptions": [
        "Experience crystal-clear audio with our premium wireless headphones featuring active noise cancellation.",
        "Track your fitness goals with this advanced smartwatch that monitors heart rate, steps, and sleep.",
        "Never run out of power with this high-capacity portable charger that supports fast charging.",
        "Charge your devices wirelessly with this sleek and efficient charging pad.",
        "Enjoy rich, immersive sound anywhere with this portable Bluetooth speaker."
    ],
    "ui_elements": [
        "Add to Cart",
        "Buy Now",
        "Save for Later",
        "View Details",
        "Customer Reviews",
        "Compare Products",
        "Share Product"
    ]
}

TARGET_LANGUAGES = ["zh-CN", "ja-JP", "ko-KR", "es-ES", "fr-FR"]


async def batch_submit_translations(coordinator, project_id: str) -> Dict[str, List[str]]:
    """
    批量提交翻译请求。
    
    Args:
        coordinator: 协调器实例
        project_id: 项目ID
    
    Returns:
        Dict[str, List[str]]: 按内容类型分组的内容ID列表
    """
    content_ids = {}
    
    for content_type, texts in SAMPLE_CONTENT.items():
        print_step(1, f"提交 {content_type} 翻译请求 ({len(texts)} 条内容)")
        type_content_ids = []
        
        for i, text in enumerate(texts):
            namespace = f"ecommerce.{content_type}"
            keys = {"category": content_type, "item_id": str(i)}
            source_payload = {"text": text}
            
            content_id = await coordinator.request_translation(
                project_id=project_id,
                namespace=namespace,
                keys=keys,
                source_payload=source_payload,
                target_langs=TARGET_LANGUAGES,
            )
            type_content_ids.append(content_id)
        
        content_ids[content_type] = type_content_ids
        print_success(f"{content_type} 请求已提交", count=len(type_content_ids))
    
    return content_ids


async def simulate_batch_processing(content_ids: Dict[str, List[str]]) -> None:
    """
    模拟批量翻译处理。
    
    Args:
        content_ids: 内容ID字典
    """
    print_step(2, "模拟批量翻译引擎处理")
    
    # 模拟翻译映射（简化版）
    # translation_map = {
    #     "zh-CN": {
    #         "Premium Wireless Headphones": "高级无线耳机",
    #         "Add to Cart": "添加到购物车",
    #         "Experience crystal-clear audio": "体验水晶般清晰的音频"
    #     },
    #     "ja-JP": {
    #         "Premium Wireless Headphones": "プレミアムワイヤレスヘッドフォン",
    #         "Add to Cart": "カートに追加",
    #         "Experience crystal-clear audio": "クリスタルクリアなオーディオを体験"
    #     },
    #     "es-ES": {
    #         "Premium Wireless Headphones": "Auriculares Inalámbricos Premium",
    #         "Add to Cart": "Añadir al Carrito",
    #         "Experience crystal-clear audio": "Experimenta audio cristalino"
    #     }
    # }
    
    total_translations = sum(len(ids) for ids in content_ids.values()) * len(TARGET_LANGUAGES)
    print_success("批量翻译处理完成", 
                 total_requests=total_translations,
                 languages=len(TARGET_LANGUAGES),
                 content_types=len(content_ids))


async def simulate_quality_review(content_ids: Dict[str, List[str]]) -> None:
    """
    模拟质量审核流程。
    
    Args:
        content_ids: 内容ID字典
    """
    print_step(3, "模拟质量审核流程")
    
    # 模拟审核统计
    review_stats = {
        "approved": 0,
        "needs_revision": 0,
        "rejected": 0
    }
    
    for content_type, ids in content_ids.items():
        for content_id in ids:
            for lang in TARGET_LANGUAGES:
                # 模拟审核结果（大部分通过）
                import random
                outcome = random.choices(
                    ["approved", "needs_revision", "rejected"],
                    weights=[0.8, 0.15, 0.05]
                )[0]
                review_stats[outcome] += 1
    
    print_success("质量审核完成", **review_stats)


async def simulate_batch_publishing(content_ids: Dict[str, List[str]]) -> None:
    """
    模拟批量发布。
    
    Args:
        content_ids: 内容ID字典
    """
    print_step(4, "模拟批量发布")
    
    published_count = 0
    for content_type, ids in content_ids.items():
        for content_id in ids:
            for lang in TARGET_LANGUAGES:
                # 模拟发布操作
                # success = await coordinator.publish_translation(revision_id)
                published_count += 1
    
    print_success("批量发布完成", published_translations=published_count)


async def verify_translations(coordinator, project_id: str, content_ids: Dict[str, List[str]]) -> None:
    """
    验证已发布的翻译。
    
    Args:
        coordinator: 协调器实例
        project_id: 项目ID
        content_ids: 内容ID字典
    """
    print_step(5, "验证已发布的翻译")
    
    verification_results = {
        "found": 0,
        "missing": 0,
        "errors": 0
    }
    
    # 验证几个示例翻译
    for content_type in ["product_titles", "ui_elements"]:
        namespace = f"ecommerce.{content_type}"
        keys = {"category": content_type, "item_id": "0"}
        
        for lang in TARGET_LANGUAGES[:2]:  # 只检查前两种语言
            try:
                translation = await coordinator.get_translation(
                    project_id=project_id,
                    namespace=namespace,
                    keys=keys,
                    target_lang=lang
                )
                
                if translation:
                    verification_results["found"] += 1
                else:
                    verification_results["missing"] += 1
                    
            except Exception:
                verification_results["errors"] += 1
    
    print_success("翻译验证完成", **verification_results)


async def generate_report(content_ids: Dict[str, List[str]]) -> None:
    """
    生成批量处理报告。
    
    Args:
        content_ids: 内容ID字典
    """
    print_section_header("批量处理报告", "📊")
    
    total_content = sum(len(ids) for ids in content_ids.values())
    total_translations = total_content * len(TARGET_LANGUAGES)
    
    print("📈 处理统计:")
    print(f"   • 内容类型: {len(content_ids)} 种")
    print(f"   • 原始内容: {total_content} 条")
    print(f"   • 目标语言: {len(TARGET_LANGUAGES)} 种")
    print(f"   • 总翻译数: {total_translations} 条")
    
    print("\n🌍 支持语言:")
    for lang in TARGET_LANGUAGES:
        print(f"   • {lang}")
    
    print("\n📦 内容分布:")
    for content_type, ids in content_ids.items():
        print(f"   • {content_type}: {len(ids)} 条")


async def main() -> None:
    """执行批量翻译处理示例。"""
    print_section_header("批量翻译处理演示", "🏭")
    
    async with example_runner("batch_processing.db") as coordinator:
        project_id = "ecommerce-platform"
        
        # 批量提交翻译请求
        content_ids = await batch_submit_translations(coordinator, project_id)
        
        # 模拟批量处理
        await simulate_batch_processing(content_ids)
        
        # 模拟质量审核
        await simulate_quality_review(content_ids)
        
        # 模拟批量发布
        await simulate_batch_publishing(content_ids)
        
        # 验证翻译结果
        await verify_translations(coordinator, project_id, content_ids)
        
        # 生成报告
        await generate_report(content_ids)
        
        print_section_header("批量处理完成", "🎉")
        print("\n🔗 下一步: 运行 03_tm_management.py 查看翻译记忆库管理示例")


if __name__ == "__main__":
    asyncio.run(main())