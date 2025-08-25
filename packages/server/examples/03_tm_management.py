# packages/server/examples/03_tm_management.py
"""
示例 3：翻译记忆库 (TM) 管理

本示例展示了翻译记忆库的核心功能：
1. 创建和管理翻译记忆库
2. 添加翻译对到TM
3. 模糊匹配和精确匹配
4. TM复用和优化
5. 质量评分和过滤

适用于提高翻译一致性和效率的场景。
"""

import asyncio
from typing import Dict, List, Tuple

import structlog
from _shared import example_runner, print_section_header, print_step, print_success

logger = structlog.get_logger()


# 模拟已有的翻译记忆库数据
EXISTING_TM_DATA = [
    # 技术文档翻译对
    (
        "Click the Save button to save your changes.",
        "zh-CN",
        "点击保存按钮以保存您的更改。",
    ),
    ("Please enter a valid email address.", "zh-CN", "请输入有效的电子邮件地址。"),
    (
        "Your password must be at least 8 characters long.",
        "zh-CN",
        "您的密码必须至少包含8个字符。",
    ),
    ("File uploaded successfully.", "zh-CN", "文件上传成功。"),
    ("Connection timeout. Please try again.", "zh-CN", "连接超时。请重试。"),
    # 电商翻译对
    ("Add to Cart", "zh-CN", "添加到购物车"),
    ("Proceed to Checkout", "zh-CN", "前往结账"),
    ("Free shipping on orders over $50", "zh-CN", "订单满50美元免费送货"),
    ("Customer Reviews", "zh-CN", "客户评价"),
    ("Product Description", "zh-CN", "产品描述"),
    # 日语翻译对
    ("Welcome to our website", "ja-JP", "私たちのウェブサイトへようこそ"),
    ("Thank you for your purchase", "ja-JP", "ご購入ありがとうございます"),
    ("Contact Support", "ja-JP", "サポートに連絡"),
    # 西班牙语翻译对
    ("Home Page", "es-ES", "Página de Inicio"),
    ("Search Results", "es-ES", "Resultados de Búsqueda"),
    ("User Profile", "es-ES", "Perfil de Usuario"),
]

# 新的待翻译内容（用于测试匹配）
NEW_CONTENT_TO_TRANSLATE = [
    "Click the Save button to save your work.",  # 与现有TM相似
    "Please enter a valid phone number.",  # 与现有TM相似
    "Add to Wishlist",  # 与现有TM相似
    "This is a completely new sentence.",  # 完全新的内容
    "File download completed successfully.",  # 与现有TM相似
    "Welcome to our mobile app",  # 与现有TM相似
]


async def create_tm_database(coordinator, project_id: str) -> str:
    """
    创建翻译记忆库。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID

    Returns:
        str: TM数据库ID
    """
    print_step(1, "创建翻译记忆库")

    # 模拟创建TM数据库
    tm_id = f"tm_{project_id}_multilang"

    # 在实际实现中，这里会调用：
    # tm_id = await coordinator.create_tm_database(
    #     name=f"{project_id} Multilingual TM",
    #     description="多语言翻译记忆库",
    #     source_lang="en-US",
    #     target_langs=["zh-CN", "ja-JP", "es-ES"]
    # )

    print_success("翻译记忆库创建完成", tm_id=tm_id)
    return tm_id


async def populate_tm_database(coordinator, tm_id: str) -> None:
    """
    向TM数据库添加翻译对。

    Args:
        coordinator: 协调器实例
        tm_id: TM数据库ID
    """
    print_step(2, f"向TM数据库添加 {len(EXISTING_TM_DATA)} 条翻译对")

    added_count = 0
    for source_text, target_lang, target_text in EXISTING_TM_DATA:
        # 在实际实现中，这里会调用：
        # await coordinator.add_tm_entry(
        #     tm_id=tm_id,
        #     source_text=source_text,
        #     target_text=target_text,
        #     source_lang="en-US",
        #     target_lang=target_lang,
        #     quality_score=0.95
        # )
        added_count += 1

    print_success("TM数据库填充完成", entries_added=added_count)


def calculate_fuzzy_match_score(source: str, target: str) -> float:
    """
    计算模糊匹配分数（简化版）。

    Args:
        source: 源文本
        target: 目标文本

    Returns:
        float: 匹配分数 (0.0 - 1.0)
    """
    # 简化的相似度计算
    source_words = set(source.lower().split())
    target_words = set(target.lower().split())

    if not source_words or not target_words:
        return 0.0

    intersection = source_words.intersection(target_words)
    union = source_words.union(target_words)

    return len(intersection) / len(union)


async def perform_tm_matching(
    coordinator, tm_id: str
) -> Dict[str, List[Tuple[str, float, str]]]:
    """
    对新内容执行TM匹配。

    Args:
        coordinator: 协调器实例
        tm_id: TM数据库ID

    Returns:
        Dict[str, List[Tuple[str, float, str]]]: 匹配结果
    """
    print_step(3, "执行TM匹配分析")

    match_results = {}

    for new_text in NEW_CONTENT_TO_TRANSLATE:
        matches = []

        # 对每个现有TM条目计算匹配分数
        for source_text, target_lang, target_text in EXISTING_TM_DATA:
            if target_lang == "zh-CN":  # 只匹配中文翻译
                score = calculate_fuzzy_match_score(new_text, source_text)
                if score > 0.3:  # 只保留相关性较高的匹配
                    matches.append((source_text, score, target_text))

        # 按匹配分数排序
        matches.sort(key=lambda x: x[1], reverse=True)
        match_results[new_text] = matches[:3]  # 只保留前3个匹配

    print_success("TM匹配完成", processed_texts=len(NEW_CONTENT_TO_TRANSLATE))
    return match_results


async def display_match_results(
    match_results: Dict[str, List[Tuple[str, float, str]]],
) -> None:
    """
    显示匹配结果。

    Args:
        match_results: 匹配结果字典
    """
    print_section_header("TM匹配结果分析", "🔍")

    for i, (new_text, matches) in enumerate(match_results.items(), 1):
        logger.info("待翻译文本", 序号=i, 文本=new_text)

        if not matches:
            logger.warning("无匹配结果 - 需要新翻译")
            continue

        logger.info("TM匹配结果")
        for j, (source, score, target) in enumerate(matches, 1):
            match_type = (
                "🟢 精确匹配"
                if score >= 0.9
                else "🟡 模糊匹配"
                if score >= 0.7
                else "🟠 低相似度"
            )
            logger.info(
                "匹配项",
                序号=j,
                匹配类型=match_type,
                相似度=f"{score:.1%}",
                源文本=source,
                建议译文=target,
            )


async def simulate_tm_optimization(coordinator, tm_id: str) -> None:
    """
    模拟TM优化过程。

    Args:
        coordinator: 协调器实例
        tm_id: TM数据库ID
    """
    print_step(4, "执行TM优化")

    optimization_stats = {
        "duplicates_removed": 3,
        "low_quality_filtered": 2,
        "entries_merged": 1,
        "final_count": len(EXISTING_TM_DATA) - 6,
    }

    # 在实际实现中，这里会执行：
    # - 重复条目检测和合并
    # - 低质量翻译过滤
    # - 相似条目合并
    # - 质量评分更新

    print_success("TM优化完成", **optimization_stats)


async def generate_tm_statistics(
    match_results: Dict[str, List[Tuple[str, float, str]]],
) -> None:
    """
    生成TM使用统计。

    Args:
        match_results: 匹配结果字典
    """
    print_section_header("TM使用统计", "📊")

    total_texts = len(match_results)
    exact_matches = 0
    fuzzy_matches = 0
    no_matches = 0

    for matches in match_results.values():
        if not matches:
            no_matches += 1
        elif matches[0][1] >= 0.9:
            exact_matches += 1
        else:
            fuzzy_matches += 1

    print("📈 匹配统计:")
    print(f"   • 总文本数: {total_texts}")
    print(f"   • 精确匹配: {exact_matches} ({exact_matches / total_texts:.1%})")
    print(f"   • 模糊匹配: {fuzzy_matches} ({fuzzy_matches / total_texts:.1%})")
    print(f"   • 无匹配: {no_matches} ({no_matches / total_texts:.1%})")

    potential_savings = (exact_matches + fuzzy_matches * 0.5) / total_texts
    print(f"\n💰 预估效率提升: {potential_savings:.1%}")

    print("\n🎯 TM数据库状态:")
    print(f"   • 总条目数: {len(EXISTING_TM_DATA)}")
    print("   • 支持语言: zh-CN, ja-JP, es-ES")
    print("   • 平均质量分: 95%")


async def demonstrate_tm_workflow(coordinator, project_id: str) -> None:
    """
    演示完整的TM工作流程。

    Args:
        coordinator: 协调器实例
        project_id: 项目ID
    """
    print_step(5, "演示TM辅助翻译工作流")

    # 模拟使用TM进行翻译
    workflow_stats = {
        "tm_suggestions_used": 4,
        "manual_translations": 2,
        "time_saved_minutes": 15,
        "consistency_score": 0.92,
    }

    print("\n🔄 TM辅助翻译流程:")
    print("   1. 提取待翻译文本")
    print("   2. 查询TM数据库")
    print("   3. 应用高质量匹配")
    print("   4. 人工审核和调整")
    print("   5. 更新TM数据库")

    print_success("TM工作流演示完成", **workflow_stats)


async def main() -> None:
    """执行TM管理示例。"""
    print_section_header("翻译记忆库管理演示", "🧠")

    async with example_runner("tm_management.db") as coordinator:
        project_id = "multilingual-platform"

        # 创建TM数据库
        tm_id = await create_tm_database(coordinator, project_id)

        # 填充TM数据库
        await populate_tm_database(coordinator, tm_id)

        # 执行TM匹配
        match_results = await perform_tm_matching(coordinator, tm_id)

        # 显示匹配结果
        await display_match_results(match_results)

        # TM优化
        await simulate_tm_optimization(coordinator, tm_id)

        # 生成统计报告
        await generate_tm_statistics(match_results)

        # 演示完整工作流
        await demonstrate_tm_workflow(coordinator, project_id)

        print_section_header("TM管理完成", "🎉")
        print("\n🔗 下一步: 运行 04_collaboration_workflow.py 查看协作工作流示例")


if __name__ == "__main__":
    asyncio.run(main())
