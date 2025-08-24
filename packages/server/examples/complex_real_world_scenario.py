# packages/server/examples/complex_real_world_scenario.py
"""
现实世界超级复杂案例：多语言电商平台本地化工作流

这个案例模拟了一个真实的电商平台本地化场景，涵盖：
1. 多项目管理（主站、移动端、营销活动）
2. 复杂的语言回退链配置
3. 多变体支持（地区差异化）
4. TM复用与一致性保证
5. 协作评审工作流
6. 批量翻译与增量更新
7. 质量控制与状态管理
8. 紧急发布与回滚场景

[v3.0.0 重构版] - 使用新的服务架构和UoW模式
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from trans_hub.core.types import TranslationStatus
from _shared import example_runner

console = Console()
logger = structlog.get_logger("complex_scenario")


class ECommerceLocalizationScenario:
    """
    电商平台本地化场景管理器
    """

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.projects = {
            "main_site": "电商主站",
            "mobile_app": "移动应用",
            "marketing": "营销活动"
        }
        self.languages = {
            "zh-CN": "简体中文",
            "zh-TW": "繁体中文",
            "en-US": "美式英语",
            "en-GB": "英式英语",
            "ja-JP": "日语",
            "ko-KR": "韩语",
            "es-ES": "西班牙语",
            "es-MX": "墨西哥西班牙语",
            "fr-FR": "法语",
            "de-DE": "德语"
        }
        self.variants = {
            "-": "默认变体",
            "formal": "正式语调",
            "casual": "轻松语调",
            "technical": "技术文档",
            "marketing": "营销推广"
        }

    async def run_complete_scenario(self):
        """
        运行完整的复杂场景
        """
        console.print(Panel.fit(
            "🌍 电商平台本地化工作流演示\n"
            "模拟真实的多语言、多项目、多变体翻译场景",
            title="Trans-Hub 复杂案例",
            border_style="blue"
        ))

        # 阶段1：项目初始化与配置
        await self._phase_1_project_setup()
        
        # 阶段2：批量内容导入
        await self._phase_2_content_import()
        
        # 阶段3：翻译请求与处理
        await self._phase_3_translation_processing()
        
        # 阶段4：协作评审工作流
        await self._phase_4_collaborative_review()
        
        # 阶段5：TM复用与一致性
        await self._phase_5_tm_consistency()
        
        # 阶段6：紧急更新场景
        await self._phase_6_emergency_update()
        
        # 阶段7：质量分析与报告
        await self._phase_7_quality_analysis()

    async def _phase_1_project_setup(self):
        """
        阶段1：项目初始化与语言回退配置
        """
        console.print("\n📋 [bold blue]阶段1: 项目初始化与配置[/bold blue]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("配置项目和语言回退链...", total=None)
            
            # 模拟复杂的语言回退配置
            fallback_configs = {
                "zh-TW": ["zh-CN", "en-US"],  # 繁体中文回退到简体中文，再到美式英语
                "en-GB": ["en-US"],           # 英式英语回退到美式英语
                "es-MX": ["es-ES", "en-US"],  # 墨西哥西语回退到西班牙语，再到美式英语
                "ko-KR": ["ja-JP", "zh-CN", "en-US"],  # 韩语回退链
                "de-DE": ["en-US"],           # 德语回退到美式英语
                "fr-FR": ["en-US"]            # 法语回退到美式英语
            }
            
            # 这里应该调用配置API，但由于当前架构限制，我们记录配置意图
            logger.info("语言回退配置已设定", fallback_configs=fallback_configs)
            
            await asyncio.sleep(1)  # 模拟配置时间
            progress.update(task, description="✅ 项目配置完成")

    async def _phase_2_content_import(self):
        """
        阶段2：批量内容导入（模拟真实电商内容）
        """
        console.print("\n📦 [bold blue]阶段2: 批量内容导入[/bold blue]")
        
        # 真实电商内容示例
        content_batches = {
            "main_site": {
                "product_titles": [
                    "无线蓝牙耳机 - 降噪版",
                    "智能手表 - 运动健康监测",
                    "便携充电宝 - 20000mAh大容量",
                    "无线充电器 - 快充支持",
                    "智能音箱 - AI语音助手"
                ],
                "product_descriptions": [
                    "采用最新降噪技术，为您带来纯净音质体验。支持蓝牙5.0，续航长达30小时。",
                    "全天候健康监测，支持50+运动模式。防水设计，适合各种运动场景。",
                    "超大容量设计，支持多设备同时充电。智能识别设备，安全快充。"
                ],
                "ui_elements": [
                    "添加到购物车",
                    "立即购买",
                    "收藏商品",
                    "查看详情",
                    "用户评价",
                    "商品对比",
                    "分享商品"
                ]
            },
            "mobile_app": {
                "notifications": [
                    "您的订单已发货，预计明天送达",
                    "限时优惠：全场8折，仅限今日",
                    "您关注的商品降价了，快来看看",
                    "新用户专享：注册即送100元优惠券"
                ],
                "error_messages": [
                    "网络连接失败，请检查网络设置",
                    "支付失败，请重试或更换支付方式",
                    "库存不足，请选择其他商品",
                    "登录已过期，请重新登录"
                ]
            },
            "marketing": {
                "campaign_slogans": [
                    "双11狂欢节 - 全年最低价",
                    "新春特惠 - 好物迎新年",
                    "夏日清仓 - 最后3天",
                    "会员专享 - 额外9折优惠"
                ],
                "email_templates": [
                    "感谢您的购买！您的订单正在处理中。",
                    "您的订单已确认，我们将尽快为您发货。",
                    "订单已发货，请注意查收。感谢您的耐心等待。"
                ]
            }
        }
        
        self.translation_requests = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            for project_key, project_name in self.projects.items():
                task = progress.add_task(f"导入 {project_name} 内容...", total=None)
                
                if project_key in content_batches:
                    for category, texts in content_batches[project_key].items():
                        for i, text in enumerate(texts):
                            content_id = f"{project_key}_{category}_{i:03d}"
                            
                            # 为不同类型内容选择合适的变体
                            variants_to_create = ["-"]  # 默认变体
                            if category in ["campaign_slogans", "email_templates"]:
                                variants_to_create.append("marketing")
                            elif category == "error_messages":
                                variants_to_create.append("technical")
                            elif category in ["product_titles", "product_descriptions"]:
                                variants_to_create.extend(["formal", "casual"])
                            
                            # 为每个目标语言和变体创建翻译请求
                            for target_lang in ["en-US", "ja-JP", "ko-KR", "es-ES", "fr-FR"]:
                                for variant in variants_to_create:
                                    try:
                                        request_id = await self.coordinator.request_translation(
                                            project_id=project_key,
                                            content_id=content_id,
                                            source_lang="zh-CN",
                                            target_lang=target_lang,
                                            variant_key=variant,
                                            source_payload={"text": text},
                                            namespace=f"{project_key}.{category}",
                                            priority="normal",
                                            requester="content_manager"
                                        )
                                        
                                        self.translation_requests.append({
                                            "request_id": request_id,
                                            "project_id": project_key,
                                            "content_id": content_id,
                                            "target_lang": target_lang,
                                            "variant": variant,
                                            "category": category,
                                            "source_text": text
                                        })
                                        
                                    except Exception as e:
                                        logger.error("翻译请求失败", 
                                                   content_id=content_id, 
                                                   target_lang=target_lang,
                                                   variant=variant,
                                                   error=str(e))
                
                progress.update(task, description=f"✅ {project_name} 内容导入完成")
                await asyncio.sleep(0.5)
        
        console.print(f"\n📊 总计创建了 {len(self.translation_requests)} 个翻译请求")

    async def _phase_3_translation_processing(self):
        """
        阶段3：翻译处理与状态管理
        """
        console.print("\n🔄 [bold blue]阶段3: 翻译处理与状态管理[/bold blue]")
        
        # 模拟翻译引擎处理（实际会由Worker自动处理）
        console.print("⚙️ 模拟翻译引擎处理中...")
        
        # 统计不同状态的翻译
        status_counts = {
            TranslationStatus.DRAFT: 0,
            TranslationStatus.REVIEWED: 0,
            TranslationStatus.PUBLISHED: 0
        }
        
        # 模拟一些翻译已完成并进入不同状态
        processed_count = min(50, len(self.translation_requests))  # 处理前50个请求
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("处理翻译请求...", total=processed_count)
            
            for i in range(processed_count):
                request = self.translation_requests[i]
                
                # 模拟不同的处理结果
                if i % 10 == 0:  # 10%的翻译需要人工审核
                    status = TranslationStatus.DRAFT
                elif i % 5 == 0:  # 20%的翻译已审核但未发布
                    status = TranslationStatus.REVIEWED
                else:  # 70%的翻译已自动发布
                    status = TranslationStatus.PUBLISHED
                
                status_counts[status] += 1
                request["status"] = status
                
                progress.update(task, advance=1, 
                              description=f"处理 {request['content_id']} ({request['target_lang']})")
                await asyncio.sleep(0.1)
        
        # 显示处理结果统计
        table = Table(title="翻译处理状态统计")
        table.add_column("状态", style="cyan")
        table.add_column("数量", style="magenta")
        table.add_column("百分比", style="green")
        
        for status, count in status_counts.items():
            percentage = (count / processed_count) * 100 if processed_count > 0 else 0
            table.add_row(
                status.value,
                str(count),
                f"{percentage:.1f}%"
            )
        
        console.print(table)

    async def _phase_4_collaborative_review(self):
        """
        阶段4：协作评审工作流
        """
        console.print("\n👥 [bold blue]阶段4: 协作评审工作流[/bold blue]")
        
        # 选择一些需要评审的翻译进行演示
        draft_requests = [r for r in self.translation_requests 
                         if r.get("status") == TranslationStatus.DRAFT][:5]
        
        if not draft_requests:
            console.print("⚠️ 没有待评审的翻译")
            return
        
        console.print(f"📝 开始评审 {len(draft_requests)} 个待审核翻译")
        
        # 模拟评审过程
        reviewers = ["linguist_alice", "pm_bob", "qa_charlie"]
        
        for i, request in enumerate(draft_requests):
            console.print(f"\n🔍 评审翻译 {i+1}/{len(draft_requests)}")
            console.print(f"   内容ID: {request['content_id']}")
            console.print(f"   目标语言: {request['target_lang']}")
            console.print(f"   变体: {request['variant']}")
            console.print(f"   原文: {request['source_text'][:50]}...")
            
            # 模拟添加评论
            reviewer = reviewers[i % len(reviewers)]
            comments = [
                "翻译质量很好，建议发布",
                "术语使用需要统一，请参考术语库",
                "语调偏正式，建议调整为更亲和的表达",
                "技术准确性良好，可以发布",
                "建议增加本地化元素，更符合目标市场习惯"
            ]
            
            try:
                # 注意：这里使用head_id，在实际场景中需要从request_id获取
                # 由于演示限制，我们使用content_id作为head_id的替代
                comment_id = await self.coordinator.add_comment(
                    head_id=request['content_id'],  # 实际应该是head_id
                    author=reviewer,
                    body=comments[i % len(comments)]
                )
                console.print(f"   💬 {reviewer}: {comments[i % len(comments)]}")
                
                # 模拟评审决策
                if i % 3 == 0:  # 33%拒绝，需要重新翻译
                    console.print("   ❌ 评审结果: 需要修改")
                else:  # 67%通过评审
                    console.print("   ✅ 评审结果: 通过，准备发布")
                    request["status"] = TranslationStatus.REVIEWED
                    
            except Exception as e:
                logger.error("评审操作失败", error=str(e))
            
            await asyncio.sleep(0.5)

    async def _phase_5_tm_consistency(self):
        """
        阶段5：TM复用与一致性检查
        """
        console.print("\n🔄 [bold blue]阶段5: TM复用与一致性保证[/bold blue]")
        
        # 模拟TM复用场景
        console.print("📚 检查翻译记忆库复用情况...")
        
        # 统计相似内容
        similar_content_groups = {
            "添加到购物车": ["添加到购物车", "加入购物车", "放入购物车"],
            "立即购买": ["立即购买", "马上购买", "现在购买"],
            "网络连接失败": ["网络连接失败", "网络连接错误", "连接失败"]
        }
        
        table = Table(title="TM复用分析")
        table.add_column("内容组", style="cyan")
        table.add_column("相似内容数", style="magenta")
        table.add_column("复用率", style="green")
        table.add_column("一致性状态", style="yellow")
        
        for group_name, similar_texts in similar_content_groups.items():
            reuse_rate = 85 + (hash(group_name) % 15)  # 模拟85-100%的复用率
            consistency = "✅ 一致" if reuse_rate > 90 else "⚠️ 需检查"
            
            table.add_row(
                group_name,
                str(len(similar_texts)),
                f"{reuse_rate}%",
                consistency
            )
        
        console.print(table)
        
        # 模拟术语一致性检查
        console.print("\n📖 术语一致性检查...")
        terminology_issues = [
            {"term": "购物车", "languages": ["en-US", "ja-JP"], "issue": "术语翻译不一致"},
            {"term": "优惠券", "languages": ["ko-KR"], "issue": "缺少本地化术语"},
            {"term": "客服", "languages": ["es-ES"], "issue": "正式度不匹配"}
        ]
        
        if terminology_issues:
            console.print("⚠️ 发现术语一致性问题:")
            for issue in terminology_issues:
                console.print(f"   • {issue['term']} ({', '.join(issue['languages'])}): {issue['issue']}")
        else:
            console.print("✅ 术语一致性检查通过")

    async def _phase_6_emergency_update(self):
        """
        阶段6：紧急更新与回滚场景
        """
        console.print("\n🚨 [bold blue]阶段6: 紧急更新场景[/bold blue]")
        
        # 模拟紧急情况：发现已发布翻译有严重错误
        console.print("⚠️ 发现紧急问题：某个产品描述翻译可能误导用户")
        
        # 选择一个已发布的翻译进行紧急处理
        published_requests = [r for r in self.translation_requests 
                            if r.get("status") == TranslationStatus.PUBLISHED][:3]
        
        if published_requests:
            emergency_request = published_requests[0]
            console.print(f"🎯 紧急处理目标: {emergency_request['content_id']}")
            console.print(f"   语言: {emergency_request['target_lang']}")
            console.print(f"   原文: {emergency_request['source_text'][:50]}...")
            
            # 步骤1：立即撤回发布
            console.print("\n📤 步骤1: 撤回已发布的翻译")
            try:
                # 注意：实际场景中需要revision_id
                # success = await self.coordinator.unpublish_translation(
                #     revision_id=emergency_request['revision_id'],
                #     actor="emergency_responder"
                # )
                console.print("   ✅ 翻译已撤回，用户将看到回退版本")
            except Exception as e:
                console.print(f"   ❌ 撤回失败: {e}")
            
            # 步骤2：创建紧急修正翻译请求
            console.print("\n🔧 步骤2: 创建紧急修正请求")
            try:
                emergency_fix_id = await self.coordinator.request_translation(
                    project_id=emergency_request['project_id'],
                    content_id=f"{emergency_request['content_id']}_emergency_fix",
                    source_lang="zh-CN",
                    target_lang=emergency_request['target_lang'],
                    variant_key=emergency_request['variant'],
                    source_payload={"text": emergency_request['source_text']},
                    namespace=f"emergency.{emergency_request['project_id']}",
                    priority="urgent",
                    requester="emergency_responder"
                )
                console.print(f"   ✅ 紧急修正请求已创建: {emergency_fix_id}")
            except Exception as e:
                console.print(f"   ❌ 创建紧急请求失败: {e}")
            
            # 步骤3：模拟快速审核和发布
            console.print("\n⚡ 步骤3: 快速审核通道")
            console.print("   👨‍💼 高级审核员介入")
            console.print("   🔍 快速质量检查")
            console.print("   ✅ 紧急修正版本已发布")
            
            await asyncio.sleep(2)
            console.print("\n🎉 紧急更新完成，服务恢复正常")
        else:
            console.print("ℹ️ 当前没有已发布的翻译可用于演示")

    async def _phase_7_quality_analysis(self):
        """
        阶段7：质量分析与报告
        """
        console.print("\n📊 [bold blue]阶段7: 质量分析与报告[/bold blue]")
        
        # 生成综合质量报告
        console.print("📈 生成质量分析报告...")
        
        # 按语言统计
        lang_stats = {}
        for request in self.translation_requests:
            lang = request.get('target_lang', 'unknown')
            if lang not in lang_stats:
                lang_stats[lang] = {'total': 0, 'completed': 0, 'quality_score': 0}
            
            lang_stats[lang]['total'] += 1
            if request.get('status') in [TranslationStatus.REVIEWED, TranslationStatus.PUBLISHED]:
                lang_stats[lang]['completed'] += 1
                # 模拟质量评分
                lang_stats[lang]['quality_score'] += 85 + (hash(request['content_id']) % 15)
        
        # 计算平均质量分数
        for lang, stats in lang_stats.items():
            if stats['completed'] > 0:
                stats['avg_quality'] = stats['quality_score'] / stats['completed']
            else:
                stats['avg_quality'] = 0
        
        # 显示语言质量报告
        table = Table(title="各语言翻译质量报告")
        table.add_column("语言", style="cyan")
        table.add_column("总数", style="magenta")
        table.add_column("完成数", style="green")
        table.add_column("完成率", style="yellow")
        table.add_column("平均质量分", style="red")
        
        for lang, stats in sorted(lang_stats.items()):
            completion_rate = (stats['completed'] / stats['total']) * 100 if stats['total'] > 0 else 0
            quality_color = "green" if stats['avg_quality'] >= 90 else "yellow" if stats['avg_quality'] >= 80 else "red"
            
            table.add_row(
                f"{lang} ({self.languages.get(lang, '未知')})",
                str(stats['total']),
                str(stats['completed']),
                f"{completion_rate:.1f}%",
                f"[{quality_color}]{stats['avg_quality']:.1f}[/{quality_color}]"
            )
        
        console.print(table)
        
        # 项目进度总览
        console.print("\n📋 项目进度总览")
        project_progress = {}
        for request in self.translation_requests:
            project = request.get('project_id', 'unknown')
            if project not in project_progress:
                project_progress[project] = {'total': 0, 'draft': 0, 'reviewed': 0, 'published': 0}
            
            project_progress[project]['total'] += 1
            status = request.get('status')
            if status == TranslationStatus.DRAFT:
                project_progress[project]['draft'] += 1
            elif status == TranslationStatus.REVIEWED:
                project_progress[project]['reviewed'] += 1
            elif status == TranslationStatus.PUBLISHED:
                project_progress[project]['published'] += 1
        
        for project, stats in project_progress.items():
            project_name = self.projects.get(project, project)
            console.print(f"\n🏢 {project_name}:")
            console.print(f"   📊 总计: {stats['total']} | "
                         f"📝 草稿: {stats['draft']} | "
                         f"✅ 已审核: {stats['reviewed']} | "
                         f"🚀 已发布: {stats['published']}")
            
            if stats['total'] > 0:
                published_rate = (stats['published'] / stats['total']) * 100
                console.print(f"   📈 发布率: {published_rate:.1f}%")
        
        # 生成改进建议
        console.print("\n💡 [bold yellow]改进建议[/bold yellow]")
        suggestions = [
            "🎯 优先处理日语和韩语的待审核翻译，提高亚洲市场覆盖率",
            "📚 建立术语库管理流程，确保技术术语翻译一致性",
            "🔄 设置自动化质量检查规则，减少人工审核工作量",
            "📱 移动端内容翻译优先级较低，建议增加资源投入",
            "🌍 考虑增加更多地区变体，提升本地化体验"
        ]
        
        for suggestion in suggestions:
            console.print(f"   {suggestion}")


async def main():
    """
    主函数：运行复杂的电商本地化场景
    """
    async with example_runner("complex_scenario.db") as coordinator:
        scenario = ECommerceLocalizationScenario(coordinator)
        await scenario.run_complete_scenario()
        
        console.print("\n" + "="*80)
        console.print(Panel.fit(
            "🎉 复杂场景演示完成！\n\n"
            "本案例展示了Trans-Hub在真实电商环境中的应用：\n"
            "• 多项目、多语言、多变体管理\n"
            "• 批量翻译与增量更新\n"
            "• 协作评审与质量控制\n"
            "• TM复用与一致性保证\n"
            "• 紧急响应与回滚机制\n"
            "• 全面的质量分析与报告\n\n"
            "这些功能组合使用，能够支撑大规模的国际化项目。",
            title="演示总结",
            border_style="green"
        ))


if __name__ == "__main__":
    asyncio.run(main())