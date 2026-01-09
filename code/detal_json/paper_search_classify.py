#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
论文检索和分类系统（改进版）
1. 从多个JSON文件中按关键词搜索论文
2. 调用大模型API对论文进行分类（支持分批处理）
3. 为每个分类生成总结文本
4. 保存分类结果到单独的JSON文件
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import time
from abc import ABC, abstractmethod


@dataclass
class Paper:
    """论文数据模型"""
    title: str
    abstract: str
    venue: str
    paper_id: Optional[str] = None
    authors: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    pdf_url: Optional[str] = None
    forum_url: Optional[str] = None


@dataclass
class ClassificationResult:
    """分类结果模型"""
    category: str
    papers: List[Paper]
    summary: str


class LLMProvider(ABC):
    """大模型提供商抽象基类"""

    @abstractmethod
    def classify_papers(self, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """
        对论文进行分类，支持增量分类

        Args:
            papers: 待分类的论文列表
            existing_categories: 已有的分类结果（用于增量分类）
        """
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API 提供商"""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview", batch_size: int = 20):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        try:
            import openai
            openai.api_key = api_key
            self.client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("请先安装 openai: pip install openai")

    def classify_papers(self, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """使用OpenAI分类论文，支持分批处理和增量分类"""
        if not papers:
            return []

        all_results = existing_categories[:] if existing_categories else []
        batch_count = (len(papers) + self.batch_size - 1) // self.batch_size

        print(f"\n正在分批处理论文（共 {batch_count} 批，每批 {self.batch_size} 篇）...")
        print(f"已有分类数: {len(all_results)}")

        for batch_idx in range(batch_count):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(papers))
            batch_papers = papers[start_idx:end_idx]

            print(f"  处理批次 {batch_idx + 1}/{batch_count}（论文 {start_idx + 1}-{end_idx}）...")

            try:
                papers_text = self._format_papers(batch_papers)
                prompt = self._create_classification_prompt(papers_text, all_results)

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的论文分析和分类专家。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=3000
                )

                result_text = response.choices[0].message.content
                batch_results = self._parse_classification_result(result_text, batch_papers, all_results)
                all_results = self._merge_results(all_results, batch_results)
                print(f"    当前分类总数: {len(all_results)}")

            except Exception as e:
                print(f"  ✗ 批次 {batch_idx + 1} 处理失败: {str(e)}")
                raise

        return all_results

    def _format_papers(self, papers: List[Paper]) -> str:
        """格式化论文列表"""
        result = []
        for i, paper in enumerate(papers, 1):
            result.append(f"""
论文 {i}:
标题: {paper.title}
会议: {paper.venue}
摘要: {paper.abstract}
""")
        return "\n".join(result)

    def _create_classification_prompt(self, papers_text: str, existing_categories: Optional[List[ClassificationResult]] = None) -> str:
        """创建分类提示词，支持增量分类"""
        existing_info = ""
        if existing_categories and len(existing_categories) > 0:
            existing_info = "\n## 已有的分类类别\n请参考以下已有分类，尝试将新论文分配到现有类别，只有在确实无法分配时才创建新类别：\n\n"
            for i, cat in enumerate(existing_categories, 1):
                existing_info += f"{i}. {cat.category} ({len(cat.papers)} 篇论文)\n"
                existing_info += f"   描述: {cat.summary[:100]}...\n"

        return f"""
请根据以下论文的标题、会议和摘要信息，将它们按照研究方向和主题进行分类。
{existing_info}

**重要说明**：
- 优先将新论文分配到现有的相关分类
- 只有在新论文的内容与所有现有分类都不符时，才创建新的分类
- 这样可以确保相同或相似研究方向的论文被分到同一类
- 避免创建过多的细分类别

论文列表：
{papers_text}

请按照以下JSON格式返回结果（只需要包含新的分类或现有分类的变化）：
{{
  "categories": [
    {{
      "name": "现有类别名称或新类别名称",
      "is_existing": true,
      "paper_indices": [1, 2, 3],
      "summary": "（如果是现有类别可省略；如果是新类别则必须提供150-200字的中文描述）"
    }}
  ]
}}

要求：
1. 如果是现有分类，设置 "is_existing": true，paper_indices 和 summary 可省略
2. 如果是新分类，设置 "is_existing": false，必须提供 summary（150-200字中文描述）
3. paper_indices 是论文在上面列表中的序号（从1开始）
4. 优先使用现有分类，确保分类数量不会无限增长
"""

    def _parse_classification_result(self, response_text: str, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """解析分类结果，支持增量分类"""
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError("无法从响应中提取JSON内容")

        try:
            result_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {str(e)}")

        results = []
        for cat in result_data.get("categories", []):
            category_name = cat.get("name", "未命名类别")
            paper_indices = cat.get("paper_indices", [])
            summary = cat.get("summary", "")
            is_existing = cat.get("is_existing", False)

            category_papers = [papers[idx - 1] for idx in paper_indices if 0 < idx <= len(papers)]

            results.append(ClassificationResult(
                category=category_name,
                papers=category_papers,
                summary=summary
            ))

        return results

    def _merge_results(self, existing_results: List[ClassificationResult], batch_results: List[ClassificationResult]) -> List[ClassificationResult]:
        """合并现有分类结果和新批次的分类结果"""
        merged = existing_results[:]

        for batch_cat in batch_results:
            # 查找是否已存在相同名称的分类
            found = False
            for i, existing_cat in enumerate(merged):
                if existing_cat.category == batch_cat.category:
                    # 将新论文添加到现有分类
                    merged[i].papers.extend(batch_cat.papers)
                    found = True
                    break

            if not found:
                # 创建新分类
                merged.append(batch_cat)

        return merged


class GeminiProvider(LLMProvider):
    """Google Gemini API 提供商"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", batch_size: int = 20):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model)
        except ImportError:
            raise ImportError("请先安装 google-generativeai: pip install google-generativeai")

    def classify_papers(self, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """使用Gemini分类论文，支持分批处理和增量分类"""
        if not papers:
            return []

        all_results = existing_categories[:] if existing_categories else []
        batch_count = (len(papers) + self.batch_size - 1) // self.batch_size

        print(f"\n正在分批处理论文（共 {batch_count} 批，每批 {self.batch_size} 篇）...")
        print(f"已有分类数: {len(all_results)}")

        for batch_idx in range(batch_count):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(papers))
            batch_papers = papers[start_idx:end_idx]

            print(f"  处理批次 {batch_idx + 1}/{batch_count}（论文 {start_idx + 1}-{end_idx}）...")

            try:
                papers_text = self._format_papers(batch_papers)
                prompt = self._create_classification_prompt(papers_text, all_results)

                response = self.client.generate_content(prompt)
                result_text = response.text
                batch_results = self._parse_classification_result(result_text, batch_papers, all_results)
                all_results = self._merge_results(all_results, batch_results)
                print(f"    当前分类总数: {len(all_results)}")

            except Exception as e:
                print(f"  ✗ 批次 {batch_idx + 1} 处理失败: {str(e)}")
                raise

        return all_results

    def _format_papers(self, papers: List[Paper]) -> str:
        """格式化论文列表"""
        result = []
        for i, paper in enumerate(papers, 1):
            result.append(f"""
论文 {i}:
标题: {paper.title}
会议: {paper.venue}
摘要: {paper.abstract}
""")
        return "\n".join(result)

    def _create_classification_prompt(self, papers_text: str, existing_categories: Optional[List[ClassificationResult]] = None) -> str:
        """创建分类提示词，支持增量分类"""
        existing_info = ""
        if existing_categories and len(existing_categories) > 0:
            existing_info = "\n## 已有的分类类别\n请参考以下已有分类，尝试将新论文分配到现有类别，只有在确实无法分配时才创建新类别：\n\n"
            for i, cat in enumerate(existing_categories, 1):
                existing_info += f"{i}. {cat.category} ({len(cat.papers)} 篇论文)\n"
                existing_info += f"   描述: {cat.summary[:100]}...\n"

        return f"""
请根据以下论文的标题、会议和摘要信息，将它们按照研究方向和主题进行分类。
{existing_info}

**重要说明**：
- 优先将新论文分配到现有的相关分类
- 只有在新论文的内容与所有现有分类都不符时，才创建新的分类
- 这样可以确保相同或相似研究方向的论文被分到同一类
- 避免创建过多的细分类别

论文列表：
{papers_text}

请按照以下JSON格式返回结果（只需要包含新的分类或现有分类的变化）：
{{
  "categories": [
    {{
      "name": "现有类别名称或新类别名称",
      "is_existing": true,
      "paper_indices": [1, 2, 3],
      "summary": "（如果是现有类别可省略；如果是新类别则必须提供150-200字的中文描述）"
    }}
  ]
}}

要求：
1. 如果是现有分类，设置 "is_existing": true，paper_indices 和 summary 可省略
2. 如果是新分类，设置 "is_existing": false，必须提供 summary（150-200字中文描述）
3. paper_indices 是论文在上面列表中的序号（从1开始）
4. 优先使用现有分类，确保分类数量不会无限增长
"""

    def _parse_classification_result(self, response_text: str, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """解析分类结果，支持增量分类"""
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError("无法从响应中提取JSON内容")

        try:
            result_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {str(e)}")

        results = []
        for cat in result_data.get("categories", []):
            category_name = cat.get("name", "未命名类别")
            paper_indices = cat.get("paper_indices", [])
            summary = cat.get("summary", "")
            is_existing = cat.get("is_existing", False)

            category_papers = [papers[idx - 1] for idx in paper_indices if 0 < idx <= len(papers)]

            results.append(ClassificationResult(
                category=category_name,
                papers=category_papers,
                summary=summary
            ))

        return results

    def _merge_results(self, existing_results: List[ClassificationResult], batch_results: List[ClassificationResult]) -> List[ClassificationResult]:
        """合并现有分类结果和新批次的分类结果"""
        merged = existing_results[:]

        for batch_cat in batch_results:
            # 查找是否已存在相同名称的分类
            found = False
            for i, existing_cat in enumerate(merged):
                if existing_cat.category == batch_cat.category:
                    # 将新论文添加到现有分类
                    merged[i].papers.extend(batch_cat.papers)
                    found = True
                    break

            if not found:
                # 创建新分类
                merged.append(batch_cat)

        return merged


class DeepSeekProvider(LLMProvider):
    """DeepSeek API 提供商"""

    def __init__(self, api_key: str, model: str = "deepseek-chat", batch_size: int = 20):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        except ImportError:
            raise ImportError("请先安装 openai: pip install openai")

    def classify_papers(self, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """使用DeepSeek分类论文，支持分批处理和增量分类"""
        if not papers:
            return []

        all_results = existing_categories[:] if existing_categories else []
        batch_count = (len(papers) + self.batch_size - 1) // self.batch_size

        print(f"\n正在分批处理论文（共 {batch_count} 批，每批 {self.batch_size} 篇）...")
        print(f"已有分类数: {len(all_results)}")

        for batch_idx in range(batch_count):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(papers))
            batch_papers = papers[start_idx:end_idx]

            print(f"  处理批次 {batch_idx + 1}/{batch_count}（论文 {start_idx + 1}-{end_idx}）...")

            try:
                papers_text = self._format_papers(batch_papers)
                prompt = self._create_classification_prompt(papers_text, all_results)

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的论文分析和分类专家。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )

                result_text = response.choices[0].message.content
                batch_results = self._parse_classification_result(result_text, batch_papers, all_results)
                all_results = self._merge_results(all_results, batch_results)
                print(f"    当前分类总数: {len(all_results)}")

                time.sleep(1)

            except Exception as e:
                print(f"  ✗ 批次 {batch_idx + 1} 处理失败: {str(e)}")
                raise

        return all_results

    def _format_papers(self, papers: List[Paper]) -> str:
        """格式化论文列表"""
        result = []
        for i, paper in enumerate(papers, 1):
            result.append(f"""
论文 {i}:
标题: {paper.title}
会议: {paper.venue}
摘要: {paper.abstract}
""")
        return "\n".join(result)

    def _create_classification_prompt(self, papers_text: str, existing_categories: Optional[List[ClassificationResult]] = None) -> str:
        """创建分类提示词，支持增量分类"""
        existing_info = ""
        if existing_categories and len(existing_categories) > 0:
            existing_info = "\n## 已有的分类类别\n请参考以下已有分类，尝试将新论文分配到现有类别，只有在确实无法分配时才创建新类别：\n\n"
            for i, cat in enumerate(existing_categories, 1):
                existing_info += f"{i}. {cat.category} ({len(cat.papers)} 篇论文)\n"
                existing_info += f"   描述: {cat.summary[:100]}...\n"

        return f"""
请根据以下论文的标题、会议和摘要信息，将它们按照研究方向和主题进行分类。
{existing_info}

**重要说明**：
- 优先将新论文分配到现有的相关分类
- 只有在新论文的内容与所有现有分类都不符时，才创建新的分类
- 这样可以确保相同或相似研究方向的论文被分到同一类
- 避免创建过多的细分类别, 建议分类名称比如“大模型rl算法优化”，“智能体rl算法优化”，“强化学习算法设计”，“多智能体推理强化学习方法”

论文列表：
{papers_text}

请按照以下JSON格式返回结果（只需要包含新的分类或现有分类的变化）：
{{
  "categories": [
    {{
      "name": "现有类别名称或新类别名称，比如“agent推理rl算法优化”，“增强工具的rl算法优化” ，“多智能体的rl算法优化” ",
      "is_existing": true,
      "paper_indices": [1, 2, 3],
      "summary": "（如果是现有类别可省略；如果是新类别则必须提供150-200字的中文描述）"
    }}
  ]
}}

要求：
1. 如果是现有分类，设置 "is_existing": true，paper_indices 和 summary 可省略
2. 如果是新分类，设置 "is_existing": false，必须提供 summary（150-200字中文描述）
3. paper_indices 是论文在上面列表中的序号（从1开始）
4. 优先使用现有分类，确保分类数量不会无限增长
"""

    def _parse_classification_result(self, response_text: str, papers: List[Paper], existing_categories: Optional[List[ClassificationResult]] = None) -> List[ClassificationResult]:
        """解析分类结果，支持增量分类"""
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError("无法从响应中提取JSON内容")

        try:
            result_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {str(e)}")

        results = []
        for cat in result_data.get("categories", []):
            category_name = cat.get("name", "未命名类别")
            paper_indices = cat.get("paper_indices", [])
            summary = cat.get("summary", "")
            is_existing = cat.get("is_existing", False)

            category_papers = [papers[idx - 1] for idx in paper_indices if 0 < idx <= len(papers)]

            results.append(ClassificationResult(
                category=category_name,
                papers=category_papers,
                summary=summary
            ))

        return results

    def _merge_results(self, existing_results: List[ClassificationResult], batch_results: List[ClassificationResult]) -> List[ClassificationResult]:
        """合并现有分类结果和新批次的分类结果"""
        merged = existing_results[:]

        for batch_cat in batch_results:
            # 查找是否已存在相同名称的分类
            found = False
            for i, existing_cat in enumerate(merged):
                if existing_cat.category == batch_cat.category:
                    # 将新论文添加到现有分类
                    merged[i].papers.extend(batch_cat.papers)
                    found = True
                    break

            if not found:
                # 创建新分类
                merged.append(batch_cat)

        return merged


class PaperSearchClassifier:
    """论文搜索和分类器"""

    def __init__(self, json_files: List[str], output_dir: str = "output"):
        self.json_files = json_files
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.papers_by_venue: Dict[str, List[Paper]] = {}

    def load_papers(self) -> None:
        """加载所有JSON文件中的论文"""
        print("正在加载论文数据...")

        for json_file in self.json_files:
            if not Path(json_file).exists():
                print(f"  警告: 文件不存在: {json_file}")
                continue

            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                venue = self._extract_venue_name(json_file)
                papers = self._parse_papers(data, venue)

                self.papers_by_venue[venue] = papers
                print(f"  ✓ {venue}: 加载 {len(papers)} 篇论文")
            except Exception as e:
                print(f"  ✗ 加载文件失败 {json_file}: {str(e)}")

    def _extract_venue_name(self, json_file: str) -> str:
        """从文件名提取会议名称"""
        filename = Path(json_file).stem
        if 'iclr' in filename.lower():
            return 'ICLR 2025'
        elif 'neurips' or 'nips' in filename.lower():
            return 'NeurIPS 2025'
        elif 'icm' in filename.lower():
            return 'ICML 2025'
        return filename

    def _parse_papers(self, data: Any, venue: str) -> List[Paper]:
        """从JSON数据解析论文"""
        papers = []

        if isinstance(data, list):
            for item in data:
                paper = self._parse_single_paper(item, venue)
                if paper:
                    papers.append(paper)
        elif isinstance(data, dict):
            paper = self._parse_single_paper(data, venue)
            if paper:
                papers.append(paper)

        return papers

    def _parse_single_paper(self, item: Dict, venue: str) -> Optional[Paper]:
        """解析单篇论文"""
        try:
            title = item.get('title') or item.get('name') or ''
            abstract = item.get('abstract') or item.get('tldr') or ''

            if not title or not abstract:
                return None

            return Paper(
                title=title,
                abstract=abstract,
                venue=venue,
                paper_id=item.get('paper_id') or item.get('id'),
                authors=item.get('authors') or [],
                keywords=item.get('keywords') or [],
                pdf_url=item.get('pdf_url') or '',
                forum_url=item.get('forum_url') or item.get('virtualsite_url') or ''
            )
        except Exception as e:
            return None

    def search_papers(self, keyword: str, case_sensitive: bool = False) -> List[Paper]:
        """
        按关键词搜索论文
        支持多个关键词，用英文逗号分隔，使用AND逻辑（所有关键词都必须存在）

        Args:
            keyword: 搜索关键词，多个关键词用英文逗号分隔，例如: "deep learning, neural networks"
            case_sensitive: 是否大小写敏感
        """
        # 解析多个关键词
        keywords = [k.strip() for k in keyword.split(',') if k.strip()]

        if not keywords:
            print("关键词不能为空")
            return []

        print(f"\n正在按关键词搜索: {keywords}")
        print(f"搜索模式: AND（所有关键词都必须存在）\n")

        results = []

        for venue, papers in self.papers_by_venue.items():
            venue_results = []
            for paper in papers:
                abstract_text = paper.abstract if case_sensitive else paper.abstract.lower()
                title_text = paper.title if case_sensitive else paper.title.lower()

                # AND逻辑：所有关键词都必须存在于摘要或标题中
                all_keywords_found = True
                for kw in keywords:
                    search_key = kw if case_sensitive else kw.lower()
                    if search_key not in abstract_text and search_key not in title_text:
                        all_keywords_found = False
                        break

                if all_keywords_found:
                    venue_results.append(paper)
                    results.append(paper)

            if venue_results:
                print(f"  {venue}: 找到 {len(venue_results)} 篇论文")

        print(f"总计找到 {len(results)} 篇相关论文\n")
        return results

    def save_search_results(self, papers: List[Paper], keyword: str) -> str:
        """保存搜索结果到JSON文件"""
        # 清理文件名中的特殊字符
        safe_keyword = self._sanitize_filename(keyword)
        output_file = self.output_dir / f"search_results_{safe_keyword}_{int(time.time())}.json"

        data = []
        for paper in papers:
            data.append({
                'title': paper.title,
                'abstract': paper.abstract,
                'venue': paper.venue,
                'paper_id': paper.paper_id,
                'authors': paper.authors,
                'pdf_url': paper.pdf_url,
                'forum_url': paper.forum_url
            })

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"搜索结果已保存: {output_file}")
        return str(output_file)

    def classify_papers(self, papers: List[Paper], provider: LLMProvider,
                       keyword: str = "") -> List[ClassificationResult]:
        """使用LLM对论文进行分类"""
        if not papers:
            print("没有论文可分类")
            return []

        print(f"\n正在使用LLM对 {len(papers)} 篇论文进行分类...")
        print("这可能需要一些时间，请稍候...")

        try:
            results = provider.classify_papers(papers)
            print(f"✓ 分类完成，共生成 {len(results)} 个类别")
            return results
        except Exception as e:
            print(f"✗ 分类失败: {str(e)}")
            raise

    def save_classification_results(self, results: List[ClassificationResult], keyword: str,
                                   provider_name: str) -> List[str]:
        """为每个分类类别保存结果到单独的JSON文件"""
        saved_files = []
        timestamp = int(time.time())

        keyword_dir = self.output_dir / f"{keyword}_{timestamp}"
        keyword_dir.mkdir(parents=True, exist_ok=True)

        summary_file = keyword_dir / "00_classification_summary.json"
        summary_data = {
            'keyword': keyword,
            'provider': provider_name,
            'timestamp': timestamp,
            'total_papers': sum(len(r.papers) for r in results),
            'categories': []
        }

        for i, result in enumerate(results):
            category_data = {
                'name': result.category,
                'paper_count': len(result.papers),
                'summary': result.summary,
                'papers': []
            }

            for paper in result.papers:
                category_data['papers'].append({
                    'title': paper.title,
                    'abstract': paper.abstract,
                    'venue': paper.venue,
                    'authors': paper.authors,
                    'paper_id': paper.paper_id,
                    'pdf_url': paper.pdf_url,
                    'forum_url': paper.forum_url
                })

            category_filename = f"{i + 1:02d}_{self._sanitize_filename(result.category)}.json"
            category_file = keyword_dir / category_filename

            with open(category_file, 'w', encoding='utf-8') as f:
                json.dump(category_data, f, ensure_ascii=False, indent=2)

            saved_files.append(str(category_file))
            print(f"  ✓ 保存类别 '{result.category}': {category_file}")

            summary_data['categories'].append({
                'name': result.category,
                'paper_count': len(result.papers),
                'summary': result.summary,
                'file': category_filename
            })

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        saved_files.insert(0, str(summary_file))
        print(f"\n✓ 分类汇总已保存: {summary_file}")

        return saved_files

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[<>:"/\\|?*]', '_', filename)

    def run_full_pipeline(self, keyword: str, provider: LLMProvider) -> Dict[str, Any]:
        """运行完整的搜索-分类管道"""
        print("=" * 60)
        print("开始执行论文检索和分类")
        print("=" * 60)

        self.load_papers()
        papers = self.search_papers(keyword, case_sensitive=False)

        if not papers:
            print("没有找到匹配的论文")
            return {'success': False, 'papers_found': 0}

        search_result_file = self.save_search_results(papers, keyword)
        results = self.classify_papers(papers, provider, keyword)

        if not results:
            print("分类失败")
            return {'success': False, 'papers_found': len(papers)}

        saved_files = self.save_classification_results(results, keyword, provider.__class__.__name__)

        print("\n" + "=" * 60)
        print("✓ 执行完成！")
        print("=" * 60)

        return {
            'success': True,
            'papers_found': len(papers),
            'categories': len(results),
            'search_result_file': search_result_file,
            'output_files': saved_files,
            'output_dir': str(self.output_dir)
        }


def get_llm_provider(api_type: str, api_key: str, batch_size: int = 20) -> LLMProvider:
    """获取LLM提供商实例"""
    if api_type.lower() == 'openai':
        return OpenAIProvider(api_key, batch_size=batch_size)
    elif api_type.lower() == 'gemini':
        return GeminiProvider(api_key, batch_size=batch_size)
    elif api_type.lower() == 'deepseek':
        return DeepSeekProvider(api_key, batch_size=batch_size)
    else:
        raise ValueError(f"不支持的API类型: {api_type}")


def main():
    """主函数"""
    print("\n论文检索和分类系统 v2.0（支持智能分批处理）")
    print("-" * 60)

    keyword = input("请输入搜索关键词（支持多个，用英文逗号分隔，例如: deep learning, neural networks）: ").strip()
    if not keyword:
        print("关键词不能为空")
        return

    api_type = input("\n请选择LLM提供商 (openai/gemini/deepseek): ").strip().lower()
    if api_type not in ['openai', 'gemini', 'deepseek']:
        print("无效的API类型")
        return

    api_key = input(f"请输入 {api_type.upper()} API密钥: ").strip()
    if not api_key:
        print("API密钥不能为空")
        return

    batch_size_input = input("请输入每批论文数量 (默认20): ").strip()
    try:
        batch_size = int(batch_size_input) if batch_size_input else 20
    except ValueError:
        batch_size = 20

    base_dir = Path(__file__).parent.parent.parent
    json_files = [
        base_dir / '2024' /'iclr2024_all_papers_standard.json',
        base_dir / '2024' /'icm2024_all_papers_standard.json',
        base_dir / '2024' /'nips2024_all_papers_standard.json'
    ]

    output_dir = base_dir / 'output' / '2024'

    classifier = PaperSearchClassifier([str(f) for f in json_files], str(output_dir))

    try:
        provider = get_llm_provider(api_type, api_key, batch_size)
    except Exception as e:
        print(f"初始化LLM提供商失败: {str(e)}")
        return

    try:
        result = classifier.run_full_pipeline(keyword, provider)

        if result['success']:
            print(f"\n结果摘要:")
            print(f"  找到论文数: {result['papers_found']}")
            print(f"  生成分类数: {result['categories']}")
            print(f"  输出目录: {result['output_dir']}")
    except Exception as e:
        print(f"执行失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
