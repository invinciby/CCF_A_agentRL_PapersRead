#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
转换 ICML2025 JSON 格式为标准论文 JSON 格式
将 icm2025_all_papers.json 转换为 iclr25_all_papers.json 格式
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import re
import hashlib


def extract_paper_id_from_url(virtualsite_url: str) -> str:
    """从虚拟网站URL中提取论文ID"""
    match = re.search(r'/poster/(\d+)$', virtualsite_url)
    if match:
        return match.group(1)

    # 如果找不到，生成一个哈希ID
    hash_obj = hashlib.md5(virtualsite_url.encode())
    return hash_obj.hexdigest()[:10]


def parse_authors(speakers_authors_str: str) -> List[str]:
    """
    解析作者字符串为列表
    输入: "Author1, Author2, Author3"
    输出: ["Author1", "Author2", "Author3"]
    """
    if not speakers_authors_str:
        return []

    # 按逗号分割，并去除空白
    authors = [author.strip() for author in speakers_authors_str.split(',')]
    return authors


def convert_icm_to_standard(icm_paper: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 ICML 格式的论文转换为标准格式
    """
    virtualsite_url = icm_paper.get('virtualsite_url', '')
    paper_id = extract_paper_id_from_url(virtualsite_url)

    # 解析作者
    speakers_authors = icm_paper.get('speakers/authors', '')
    authors = parse_authors(speakers_authors)

    # 构造论文类型和顺序
    paper_type = icm_paper.get('type', 'poster').lower()
    type_order = {'oral': 1, 'poster': 2, 'workshop': 3}.get(paper_type, 2)

    standard_paper = {
        'paper_id': paper_id,
        'forum_url': virtualsite_url.replace('/virtual/', '/forum?id=') if '/virtual/' in virtualsite_url else virtualsite_url,
        'number': hash(paper_id) % 100000,  # 生成一个数字ID
        'version': 1,
        'submission_date': '',  # ICML数据中没有提交日期
        'title': icm_paper.get('name', ''),
        'authors': authors,
        'abstract': icm_paper.get('abstract', ''),
        'keywords': [],  # 从摘要和标题中可选地提取关键词
        'primary_area': '',  # ICML数据中没有主要领域
        'pdf_url': '',  # ICML数据中需要从虚拟网站获取
        'tldr': icm_paper.get('lay_summary', ''),  # 使用lay_summary作为tldr
        'reply_count': 0,  # ICML数据中没有回复计数
        'venue': 'ICML 2025 ' + icm_paper.get('type', 'Poster'),
        'venueid': 'ICML.cc/2025/Conference',
        'type': paper_type,
        'type_order': type_order
    }

    return standard_paper


def convert_file(input_file: str, output_file: str) -> None:
    """
    将输入文件转换为标准格式并保存
    """
    print(f"正在读取输入文件: {input_file}")

    # 读取输入JSON文件
    with open(input_file, 'r', encoding='utf-8') as f:
        icm_papers = json.load(f)

    print(f"共读取 {len(icm_papers)} 篇论文")

    # 转换每篇论文
    print("正在转换论文格式...")
    standard_papers = []
    for i, icm_paper in enumerate(icm_papers):
        try:
            standard_paper = convert_icm_to_standard(icm_paper)
            standard_papers.append(standard_paper)

            if (i + 1) % 100 == 0:
                print(f"  已转换 {i + 1}/{len(icm_papers)} 篇论文")
        except Exception as e:
            print(f"  警告: 转换第 {i + 1} 篇论文失败: {str(e)}")
            continue

    # 保存转换后的数据
    print(f"正在保存输出文件: {output_file}")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(standard_papers, f, ensure_ascii=False, indent=2)

    print(f"转换完成! 共转换 {len(standard_papers)} 篇论文")
    print(f"输出文件: {output_file}")


def main():
    """主函数"""
    # 定义文件路径
    base_dir = Path(__file__).parent.parent.parent
    input_file = base_dir / '2024' / 'nips2024_all_papers.json'
    output_file = base_dir / '2024' / 'nips2024_all_papers_standard.json'

    # 如果提供了命令行参数，使用命令行参数
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_file = Path(sys.argv[2])

    # 验证输入文件
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}")
        sys.exit(1)

    # 执行转换
    try:
        convert_file(str(input_file), str(output_file))
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
