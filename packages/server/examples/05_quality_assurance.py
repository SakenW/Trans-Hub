# packages/server/examples/05_quality_assurance.py
"""
示例 5：翻译质量保证

本示例展示了翻译质量控制的完整体系：
1. 自动化质量检查
2. 术语一致性验证
3. 格式和样式检查
4. 质量评分系统
5. 质量报告和改进建议

适用于对翻译质量有严格要求的企业级场景。
"""

import asyncio
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import structlog
from _shared import example_runner, print_section_header, print_step, print_success

logger = structlog.get_logger()


class QualityIssueType(Enum):
    """质量问题类型。"""
    TERMINOLOGY = "terminology"          # 术语不一致
    FORMATTING = "formatting"            # 格式问题
    LENGTH = "length"                    # 长度问题
    COMPLETENESS = "completeness"        # 完整性问题
    STYLE = "style"                      # 风格问题
    GRAMMAR = "grammar"                  # 语法问题


class QualitySeverity(Enum):
    """质量问题严重程度。"""
    CRITICAL = "critical"    # 严重：必须修复
    MAJOR = "major"          # 重要：建议修复
    MINOR = "minor"          # 轻微：可选修复
    INFO = "info"            # 信息：仅提示


@dataclass
class QualityIssue:
    """质量问题数据结构。"""
    type: QualityIssueType
    severity: QualitySeverity
    message: str
    position: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class QualityReport:
    """质量报告数据结构。"""
    content_id: str
    target_lang: str
    overall_score: float
    issues: List[QualityIssue]
    passed_checks: List[str]
    failed_checks: List[str]


# 术语词典
TERMINOLOGY_DICT = {
    "zh-CN": {
        "user": "用户",
        "login": "登录",
        "password": "密码",
        "database": "数据库",
        "authentication": "身份验证",
        "authorization": "授权",
        "configuration": "配置",
        "settings": "设置",
        "profile": "个人资料",
        "dashboard": "仪表板"
    },
    "ja-JP": {
        "user": "ユーザー",
        "login": "ログイン",
        "password": "パスワード",
        "database": "データベース",
        "authentication": "認証",
        "authorization": "認可",
        "configuration": "設定",
        "settings": "設定",
        "profile": "プロフィール",
        "dashboard": "ダッシュボード"
    }
}

# 测试翻译样本
TRANSLATION_SAMPLES = [
    {
        "content_id": "sample_001",
        "source_text": "Please enter your user login credentials to access the dashboard.",
        "target_lang": "zh-CN",
        "target_text": "请输入您的用户登陆凭据以访问仪表盘。",  # 故意包含错误
        "namespace": "ui.auth"
    },
    {
        "content_id": "sample_002",
        "source_text": "Database configuration settings",
        "target_lang": "zh-CN",
        "target_text": "数据库配置设置",
        "namespace": "docs.config"
    },
    {
        "content_id": "sample_003",
        "source_text": "User authentication failed. Please check your password.",
        "target_lang": "zh-CN",
        "target_text": "用户认证失败。请检查您的密码。",  # 术语不一致
        "namespace": "messages.error"
    },
    {
        "content_id": "sample_004",
        "source_text": "Login",
        "target_lang": "ja-JP",
        "target_text": "ログイン",
        "namespace": "ui.buttons"
    },
    {
        "content_id": "sample_005",
        "source_text": "This is a very long sentence that contains multiple clauses and should be checked for appropriate length in the target language to ensure readability.",
        "target_lang": "zh-CN",
        "target_text": "这是一个非常长的句子，包含多个从句，应该检查目标语言中的适当长度以确保可读性。",
        "namespace": "docs.content"
    }
]


class QualityChecker:
    """翻译质量检查器。"""
    
    def __init__(self):
        self.terminology_dict = TERMINOLOGY_DICT
    
    async def check_terminology_consistency(self, source_text: str, target_text: str, target_lang: str) -> List[QualityIssue]:
        """检查术语一致性。"""
        issues = []
        
        if target_lang not in self.terminology_dict:
            return issues
        
        terms = self.terminology_dict[target_lang]
        source_lower = source_text.lower()
        
        for english_term, correct_translation in terms.items():
            if english_term in source_lower:
                # 检查目标文本是否使用了正确的术语
                if correct_translation not in target_text:
                    # 查找可能的错误术语
                    wrong_terms = self._find_similar_terms(target_text, correct_translation)
                    if wrong_terms:
                        issue = QualityIssue(
                            type=QualityIssueType.TERMINOLOGY,
                            severity=QualitySeverity.MAJOR,
                            message=f"术语不一致：'{english_term}' 应翻译为 '{correct_translation}'，但发现了 '{wrong_terms[0]}'",
                            suggestion=f"将 '{wrong_terms[0]}' 替换为 '{correct_translation}'"
                        )
                        issues.append(issue)
        
        return issues
    
    def _find_similar_terms(self, text: str, correct_term: str) -> List[str]:
        """查找相似的错误术语。"""
        # 简化的相似术语检测
        similar_terms_map = {
            "登录": ["登陆"],
            "身份验证": ["认证", "验证"],
            "仪表板": ["仪表盘", "控制台"]
        }
        
        if correct_term in similar_terms_map:
            for wrong_term in similar_terms_map[correct_term]:
                if wrong_term in text:
                    return [wrong_term]
        
        return []
    
    async def check_formatting(self, source_text: str, target_text: str) -> List[QualityIssue]:
        """检查格式问题。"""
        issues = []
        
        # 检查标点符号
        source_punctuation = re.findall(r'[.!?]', source_text)
        target_punctuation = re.findall(r'[。！？.!?]', target_text)
        
        if len(source_punctuation) != len(target_punctuation):
            issue = QualityIssue(
                type=QualityIssueType.FORMATTING,
                severity=QualitySeverity.MINOR,
                message=f"标点符号数量不匹配：源文本 {len(source_punctuation)} 个，目标文本 {len(target_punctuation)} 个",
                suggestion="检查并调整标点符号"
            )
            issues.append(issue)
        
        # 检查空格
        if target_text.startswith(' ') or target_text.endswith(' '):
            issue = QualityIssue(
                type=QualityIssueType.FORMATTING,
                severity=QualitySeverity.MINOR,
                message="文本开头或结尾包含多余空格",
                suggestion="删除多余的空格"
            )
            issues.append(issue)
        
        return issues
    
    async def check_length_appropriateness(self, source_text: str, target_text: str, namespace: str) -> List[QualityIssue]:
        """检查长度适当性。"""
        issues = []
        
        source_len = len(source_text)
        target_len = len(target_text)
        
        # 根据命名空间设置不同的长度限制
        if namespace.startswith("ui."):
            # UI元素应该简洁
            if target_len > source_len * 1.5:
                issue = QualityIssue(
                    type=QualityIssueType.LENGTH,
                    severity=QualitySeverity.MAJOR,
                    message=f"UI文本过长：目标文本 {target_len} 字符，源文本 {source_len} 字符",
                    suggestion="考虑使用更简洁的表达"
                )
                issues.append(issue)
        elif namespace.startswith("docs."):
            # 文档可以适当扩展
            if target_len > source_len * 2.0:
                issue = QualityIssue(
                    type=QualityIssueType.LENGTH,
                    severity=QualitySeverity.MINOR,
                    message=f"文档文本较长：目标文本 {target_len} 字符，源文本 {source_len} 字符",
                    suggestion="检查是否有冗余表达"
                )
                issues.append(issue)
        
        return issues
    
    async def check_completeness(self, source_text: str, target_text: str) -> List[QualityIssue]:
        """检查翻译完整性。"""
        issues = []
        
        # 检查是否为空
        if not target_text.strip():
            issue = QualityIssue(
                type=QualityIssueType.COMPLETENESS,
                severity=QualitySeverity.CRITICAL,
                message="翻译内容为空",
                suggestion="提供完整的翻译"
            )
            issues.append(issue)
        
        # 检查是否包含未翻译的英文（简单检测）
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', target_text)
        if english_words and len(english_words) > 2:
            issue = QualityIssue(
                type=QualityIssueType.COMPLETENESS,
                severity=QualitySeverity.MAJOR,
                message=f"可能包含未翻译的英文单词：{', '.join(english_words[:3])}",
                suggestion="检查并翻译所有英文内容"
            )
            issues.append(issue)
        
        return issues
    
    async def calculate_quality_score(self, issues: List[QualityIssue]) -> float:
        """计算质量分数。"""
        if not issues:
            return 100.0
        
        # 根据问题严重程度扣分
        penalty_map = {
            QualitySeverity.CRITICAL: 30,
            QualitySeverity.MAJOR: 15,
            QualitySeverity.MINOR: 5,
            QualitySeverity.INFO: 1
        }
        
        total_penalty = sum(penalty_map[issue.severity] for issue in issues)
        score = max(0, 100 - total_penalty)
        
        return score
    
    async def generate_quality_report(self, sample: Dict) -> QualityReport:
        """生成质量报告。"""
        all_issues = []
        passed_checks = []
        failed_checks = []
        
        # 执行各项检查
        terminology_issues = await self.check_terminology_consistency(
            sample["source_text"], sample["target_text"], sample["target_lang"]
        )
        all_issues.extend(terminology_issues)
        
        formatting_issues = await self.check_formatting(
            sample["source_text"], sample["target_text"]
        )
        all_issues.extend(formatting_issues)
        
        length_issues = await self.check_length_appropriateness(
            sample["source_text"], sample["target_text"], sample["namespace"]
        )
        all_issues.extend(length_issues)
        
        completeness_issues = await self.check_completeness(
            sample["source_text"], sample["target_text"]
        )
        all_issues.extend(completeness_issues)
        
        # 统计检查结果
        check_results = {
            "术语一致性": len(terminology_issues) == 0,
            "格式规范": len(formatting_issues) == 0,
            "长度适当": len(length_issues) == 0,
            "翻译完整": len(completeness_issues) == 0
        }
        
        for check_name, passed in check_results.items():
            if passed:
                passed_checks.append(check_name)
            else:
                failed_checks.append(check_name)
        
        # 计算总分
        overall_score = await self.calculate_quality_score(all_issues)
        
        return QualityReport(
            content_id=sample["content_id"],
            target_lang=sample["target_lang"],
            overall_score=overall_score,
            issues=all_issues,
            passed_checks=passed_checks,
            failed_checks=failed_checks
        )


async def setup_quality_system(coordinator) -> QualityChecker:
    """
    设置质量保证系统。
    
    Args:
        coordinator: 协调器实例
    
    Returns:
        QualityChecker: 质量检查器实例
    """
    print_step(1, "设置质量保证系统")
    
    checker = QualityChecker()
    
    # 在实际实现中，这里会：
    # - 加载术语词典
    # - 配置质量规则
    # - 初始化检查引擎
    
    print_success("质量保证系统设置完成", 
                 terminology_entries=sum(len(terms) for terms in TERMINOLOGY_DICT.values()),
                 supported_languages=len(TERMINOLOGY_DICT))
    
    return checker


async def run_quality_checks(checker: QualityChecker) -> List[QualityReport]:
    """
    运行质量检查。
    
    Args:
        checker: 质量检查器
    
    Returns:
        List[QualityReport]: 质量报告列表
    """
    print_step(2, f"对 {len(TRANSLATION_SAMPLES)} 个翻译样本执行质量检查")
    
    reports = []
    
    for sample in TRANSLATION_SAMPLES:
        print(f"   🔍 检查: {sample['content_id']} ({sample['target_lang']})")
        report = await checker.generate_quality_report(sample)
        reports.append(report)
        
        # 显示检查结果
        if report.issues:
            print(f"      ⚠️  发现 {len(report.issues)} 个问题，质量分数: {report.overall_score:.1f}")
        else:
            print(f"      ✅ 无问题，质量分数: {report.overall_score:.1f}")
    
    print_success("质量检查完成", samples_checked=len(TRANSLATION_SAMPLES))
    return reports


async def display_quality_reports(reports: List[QualityReport]) -> None:
    """
    显示详细的质量报告。
    
    Args:
        reports: 质量报告列表
    """
    print_section_header("详细质量报告", "📋")
    
    for i, report in enumerate(reports, 1):
        sample = next(s for s in TRANSLATION_SAMPLES if s["content_id"] == report.content_id)
        
        logger.info(
            "质量报告详情",
            报告序号=i,
            内容ID=report.content_id,
            源文本=sample['source_text'],
            译文=sample['target_text'],
            语言=report.target_lang,
            质量分数=f"{report.overall_score:.1f}/100"
        )
        
        if report.passed_checks:
            logger.info("通过检查", 检查项=', '.join(report.passed_checks))
        
        if report.failed_checks:
            logger.warning("未通过检查", 检查项=', '.join(report.failed_checks))
        
        if report.issues:
            logger.info("发现的问题")
            for j, issue in enumerate(report.issues, 1):
                severity_icon = {
                    QualitySeverity.CRITICAL: "🔴",
                    QualitySeverity.MAJOR: "🟡",
                    QualitySeverity.MINOR: "🟠",
                    QualitySeverity.INFO: "🔵"
                }[issue.severity]
                
                logger.info(
                    "质量问题",
                    序号=j,
                    严重程度=severity_icon,
                    消息=issue.message,
                    建议=issue.suggestion if issue.suggestion else None
                )
        else:
            logger.info("🎉 无质量问题")


async def generate_quality_statistics(reports: List[QualityReport]) -> None:
    """
    生成质量统计信息。
    
    Args:
        reports: 质量报告列表
    """
    print_section_header("质量统计分析", "📊")
    
    # 总体统计
    total_samples = len(reports)
    avg_score = sum(r.overall_score for r in reports) / total_samples
    high_quality = sum(1 for r in reports if r.overall_score >= 90)
    medium_quality = sum(1 for r in reports if 70 <= r.overall_score < 90)
    low_quality = sum(1 for r in reports if r.overall_score < 70)
    
    print("📈 总体质量概览:")
    print(f"   • 样本总数: {total_samples}")
    print(f"   • 平均分数: {avg_score:.1f}/100")
    print(f"   • 高质量 (≥90分): {high_quality} ({high_quality/total_samples:.1%})")
    print(f"   • 中等质量 (70-89分): {medium_quality} ({medium_quality/total_samples:.1%})")
    print(f"   • 低质量 (<70分): {low_quality} ({low_quality/total_samples:.1%})")
    
    # 问题类型统计
    issue_type_counts = {}
    issue_severity_counts = {}
    
    for report in reports:
        for issue in report.issues:
            issue_type_counts[issue.type] = issue_type_counts.get(issue.type, 0) + 1
            issue_severity_counts[issue.severity] = issue_severity_counts.get(issue.severity, 0) + 1
    
    if issue_type_counts:
        print("\n🔍 问题类型分布:")
        for issue_type, count in issue_type_counts.items():
            type_name = {
                QualityIssueType.TERMINOLOGY: "术语问题",
                QualityIssueType.FORMATTING: "格式问题",
                QualityIssueType.LENGTH: "长度问题",
                QualityIssueType.COMPLETENESS: "完整性问题",
                QualityIssueType.STYLE: "风格问题",
                QualityIssueType.GRAMMAR: "语法问题"
            }[issue_type]
            print(f"   • {type_name}: {count} 次")
    
    if issue_severity_counts:
        print("\n⚠️  问题严重程度分布:")
        for severity, count in issue_severity_counts.items():
            severity_name = {
                QualitySeverity.CRITICAL: "严重",
                QualitySeverity.MAJOR: "重要",
                QualitySeverity.MINOR: "轻微",
                QualitySeverity.INFO: "信息"
            }[severity]
            print(f"   • {severity_name}: {count} 次")
    
    # 语言质量对比
    lang_scores = {}
    for report in reports:
        if report.target_lang not in lang_scores:
            lang_scores[report.target_lang] = []
        lang_scores[report.target_lang].append(report.overall_score)
    
    if len(lang_scores) > 1:
        print("\n🌍 语言质量对比:")
        for lang, scores in lang_scores.items():
            avg_lang_score = sum(scores) / len(scores)
            print(f"   • {lang}: {avg_lang_score:.1f}/100 (样本数: {len(scores)})")


async def provide_improvement_suggestions(reports: List[QualityReport]) -> None:
    """
    提供质量改进建议。
    
    Args:
        reports: 质量报告列表
    """
    print_section_header("质量改进建议", "💡")
    
    # 分析常见问题
    common_issues = {}
    for report in reports:
        for issue in report.issues:
            key = (issue.type, issue.severity)
            if key not in common_issues:
                common_issues[key] = []
            common_issues[key].append(issue.message)
    
    # 生成改进建议
    suggestions = []
    
    if QualityIssueType.TERMINOLOGY in [k[0] for k in common_issues.keys()]:
        suggestions.append("🎯 术语管理: 建立并维护统一的术语词典，确保译者使用一致的术语")
    
    if QualityIssueType.FORMATTING in [k[0] for k in common_issues.keys()]:
        suggestions.append("📝 格式规范: 制定详细的格式指南，包括标点符号和空格使用规则")
    
    if QualityIssueType.LENGTH in [k[0] for k in common_issues.keys()]:
        suggestions.append("📏 长度控制: 为不同类型的内容设置合适的长度限制和指导原则")
    
    # 通用建议
    suggestions.extend([
        "🔄 定期培训: 为译者提供质量标准和最佳实践培训",
        "🤖 自动化检查: 集成更多自动化质量检查工具",
        "👥 同行评议: 建立译者间的相互评议机制",
        "📊 持续监控: 定期分析质量趋势，及时调整策略"
    ])
    
    print("🚀 推荐的改进措施:")
    for i, suggestion in enumerate(suggestions, 1):
        print(f"   {i}. {suggestion}")
    
    # 质量目标
    print("\n🎯 质量目标建议:")
    print("   • 短期目标: 平均质量分数达到 85分")
    print("   • 中期目标: 90% 的翻译达到高质量标准 (≥90分)")
    print("   • 长期目标: 建立零缺陷的翻译质量体系")


async def main() -> None:
    """执行翻译质量保证示例。"""
    print_section_header("翻译质量保证演示", "🛡️")
    
    async with example_runner("quality_assurance.db") as coordinator:
        # 设置质量保证系统
        checker = await setup_quality_system(coordinator)
        
        # 运行质量检查
        reports = await run_quality_checks(checker)
        
        # 显示详细报告
        await display_quality_reports(reports)
        
        # 生成统计分析
        await generate_quality_statistics(reports)
        
        # 提供改进建议
        await provide_improvement_suggestions(reports)
        
        print_section_header("质量保证完成", "🎉")
        print("\n🔗 下一步: 运行 06_advanced_features.py 查看高级功能示例")


if __name__ == "__main__":
    asyncio.run(main())