#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
论文检索和分类系统 - 使用示例
演示如何使用该系统进行论文搜索和分类
"""

from paper_search_classify import (
    PaperSearchClassifier,
    OpenAIProvider,
    GeminiProvider,
    DeepSeekProvider
)
from pathlib import Path


def example_1_basic_usage():
    """示例1: 基础用法 - 使用OpenAI进行分类"""
    print("=" * 60)
    print("示例1: 基础用法 - 使用OpenAI进行分类")
    print("=" * 60)

    # 初始化分类器
    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / 'iclr25_all_papers.json',
        base_dir / 'neurips2025_all_papers.json',
        base_dir / 'icm2025_all_papers_standard.json'
    ]

    classifier = PaperSearchClassifier(
        [str(f) for f in json_files if f.exists()],
        output_dir=str(base_dir / 'output')
    )

    # 创建OpenAI提供商
    provider = OpenAIProvider(api_key='your_openai_api_key_here')

    # 运行完整流程
    result = classifier.run_full_pipeline(
        keyword='deep learning',
        provider=provider,
        num_categories=3
    )

    if result['success']:
        print(f"\n✓ 成功找到 {result['papers_found']} 篇论文")
        print(f"✓ 生成了 {result['categories']} 个分类")
        print(f"✓ 输出文件在: {result['output_dir']}")


def example_2_gemini_usage():
    """示例2: 使用Google Gemini进行分类"""
    print("\n" + "=" * 60)
    print("示例2: 使用Google Gemini进行分类")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / 'iclr25_all_papers.json',
        base_dir / 'neurips2025_all_papers.json',
    ]

    classifier = PaperSearchClassifier(
        [str(f) for f in json_files if f.exists()],
        output_dir=str(base_dir / 'output')
    )

    # 创建Gemini提供商
    provider = GeminiProvider(api_key='your_gemini_api_key_here')

    # 搜索并分类
    result = classifier.run_full_pipeline(
        keyword='transformer',
        provider=provider,
        num_categories=4
    )

    if result['success']:
        print(f"\n✓ 完成！输出目录: {result['output_dir']}")


def example_3_deepseek_usage():
    """示例3: 使用DeepSeek进行分类"""
    print("\n" + "=" * 60)
    print("示例3: 使用DeepSeek进行分类（最便宜）")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / 'icm2025_all_papers_standard.json',
    ]

    classifier = PaperSearchClassifier(
        [str(f) for f in json_files if f.exists()],
        output_dir=str(base_dir / 'output')
    )

    # 创建DeepSeek提供商
    provider = DeepSeekProvider(api_key='your_deepseek_api_key_here')

    # 搜索并分类
    result = classifier.run_full_pipeline(
        keyword='vision',
        provider=provider,
        num_categories=3
    )

    if result['success']:
        print(f"\n✓ 完成！输出目录: {result['output_dir']}")


def example_4_custom_logic():
    """示例4: 自定义搜索和分类逻辑"""
    print("\n" + "=" * 60)
    print("示例4: 自定义搜索和分类逻辑")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / 'iclr25_all_papers.json',
    ]

    classifier = PaperSearchClassifier(
        [str(f) for f in json_files if f.exists()],
        output_dir=str(base_dir / 'output')
    )

    # 手动加载论文
    classifier.load_papers()

    # 搜索论文（大小写不敏感）
    papers = classifier.search_papers(keyword='attention', case_sensitive=False)

    if papers:
        print(f"找到 {len(papers)} 篇论文")

        # 保存搜索结果
        search_file = classifier.save_search_results(papers, 'attention')
        print(f"搜索结果已保存: {search_file}")

        # 使用DeepSeek进行分类（最便宜）
        provider = DeepSeekProvider(api_key='your_deepseek_api_key_here')

        results = classifier.classify_papers(
            papers,
            provider=provider,
            num_categories=3,
            keyword='attention'
        )

        # 保存分类结果
        output_files = classifier.save_classification_results(
            results,
            keyword='attention',
            provider_name='DeepSeek'
        )

        print(f"分类结果已保存到 {len(output_files)} 个文件")
    else:
        print("未找到匹配的论文")


def example_5_batch_processing():
    """示例5: 批量处理多个关键词"""
    print("\n" + "=" * 60)
    print("示例5: 批量处理多个关键词")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / 'iclr25_all_papers.json',
        base_dir / 'neurips2025_all_papers.json',
    ]

    classifier = PaperSearchClassifier(
        [str(f) for f in json_files if f.exists()],
        output_dir=str(base_dir / 'output')
    )

    # 创建提供商（使用成本最低的DeepSeek）
    provider = DeepSeekProvider(api_key='your_deepseek_api_key_here')

    # 要搜索的关键词列表
    keywords = ['machine learning', 'neural networks', 'optimization']

    for keyword in keywords:
        print(f"\n处理关键词: {keyword}")
        try:
            result = classifier.run_full_pipeline(
                keyword=keyword,
                provider=provider,
                num_categories=3
            )

            if result['success']:
                print(f"  ✓ 完成！找到 {result['papers_found']} 篇论文")
        except Exception as e:
            print(f"  ✗ 出错: {str(e)}")

        # 为避免API限制，添加延迟
        import time
        time.sleep(2)


if __name__ == '__main__':
    """
    运行示例

    使用步骤:
    1. 替换示例中的API密钥为实际的密钥
    2. 根据需要修改关键词和参数
    3. 运行对应的示例函数

    注意:
    - 需要先安装依赖: pip install openai google-generativeai
    - 需要有有效的API密钥
    - 大模型API调用会产生费用
    """

    print("\n论文检索和分类系统 - 使用示例\n")
    print("可用的示例:")
    print("  1. example_1_basic_usage() - 基础用法（OpenAI）")
    print("  2. example_2_gemini_usage() - 使用Gemini")
    print("  3. example_3_deepseek_usage() - 使用DeepSeek（推荐）")
    print("  4. example_4_custom_logic() - 自定义逻辑")
    print("  5. example_5_batch_processing() - 批量处理")

    print("\n提示: 在IDE中打开此文件，取消注释下面的行来运行示例\n")

    # 取消下面的注释来运行示例
    # example_1_basic_usage()
    # example_2_gemini_usage()
    # example_3_deepseek_usage()
    # example_4_custom_logic()
    # example_5_batch_processing()
