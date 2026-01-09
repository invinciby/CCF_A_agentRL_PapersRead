#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
论文分类可视化和搜索系统
支持：
1. 读取分类后的JSON文件
2. 可视化展示分类结果
3. 实时搜索功能
4. 论文链接点击跳转
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

try:
    from flask import Flask, render_template_string, request, jsonify
except ImportError:
    print("请先安装 Flask: pip install flask")
    sys.exit(1)


@dataclass
class PaperInfo:
    """论文信息"""
    title: str
    abstract: str
    venue: str
    paper_id: Optional[str] = None
    authors: Optional[List[str]] = None
    pdf_url: Optional[str] = None
    forum_url: Optional[str] = None


class ClassificationVisualizer:
    """分类结果可视化器"""

    def __init__(self, data_dir: str):
        """
        初始化可视化器

        Args:
            data_dir: 包含分类结果的目录
        """
        self.data_dir = Path(data_dir)
        self.categories = {}  # {category_name: {papers: [...], summary: "..."}}
        self.all_papers = []  # 所有论文列表
        self.search_results = []
        self.available_years = []  # 可用的年份列表
        self.current_year = None  # 当前选中的年份
        self.all_year_data = {}  # 存储所有年份的数据 {year: {categories: {...}}}

    def get_available_years(self) -> List[str]:
        """
        获取可用的年份列表

        Returns:
            年份列表，按降序排列
        """
        if not self.data_dir.exists():
            return []

        years = []
        for item in self.data_dir.iterdir():
            if item.is_dir() and item.name.isdigit():
                years.append(item.name)

        return sorted(years, reverse=True)  # 按降序排列

    def load_year_data(self, year: str) -> bool:
        """
        加载特定年份的数据

        Args:
            year: 年份字符串 (如 "2025")

        Returns:
            是否成功加载
        """
        year_dir = self.data_dir / year
        if not year_dir.exists():
            print(f"错误: 年份目录不存在: {year_dir}")
            return False

        # 自动选择该年份下最新的分类结果
        subdirs = [d for d in year_dir.iterdir() if d.is_dir()]
        if not subdirs:
            print(f"错误: 在 {year_dir} 中找不到分类结果目录")
            return False

        result_dir = max(subdirs, key=lambda p: p.stat().st_mtime)
        print(f"加载 {year} 年的分类结果: {result_dir}")

        # 清空当前数据
        self.categories = {}
        self.all_papers = []

        # 加载所有分类文件
        category_files = sorted(result_dir.glob("*.json"))
        if not category_files:
            print(f"错误: 在 {result_dir} 中找不到JSON文件")
            return False

        summary_file = result_dir / "00_classification_summary.json"
        if summary_file.exists():
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            print(f"找到 {summary_data.get('total_papers', 0)} 篇论文，分为 {len(summary_data.get('categories', []))} 个类别")

            # 加载各分类文件
            for cat_info in summary_data.get('categories', []):
                cat_name = cat_info.get('name')
                cat_file = result_dir / cat_info.get('file')

                if cat_file.exists():
                    with open(cat_file, 'r', encoding='utf-8') as f:
                        cat_data = json.load(f)

                    papers = []
                    for paper_data in cat_data.get('papers', []):
                        paper = PaperInfo(
                            title=paper_data.get('title', ''),
                            abstract=paper_data.get('abstract', ''),
                            venue=paper_data.get('venue', ''),
                            paper_id=paper_data.get('paper_id'),
                            authors=paper_data.get('authors', []),
                            pdf_url=paper_data.get('pdf_url'),
                            forum_url=paper_data.get('forum_url')
                        )
                        papers.append(paper)
                        self.all_papers.append((cat_name, paper))

                    self.categories[cat_name] = {
                        'papers': papers,
                        'summary': cat_data.get('summary', ''),
                        'count': len(papers)
                    }

        self.current_year = year
        return True

    def load_classification_results(self, result_dir: Optional[str] = None) -> bool:
        """
        加载分类结果（兼容旧版本）

        Args:
            result_dir: 特定的结果目录，如果为空则自动选择最新的

        Returns:
            是否成功加载
        """
        # 获取可用年份
        self.available_years = self.get_available_years()

        if not self.available_years:
            print(f"错误: 在 {self.data_dir} 中找不到任何年份目录")
            return False

        # 加载最新年份的数据
        latest_year = self.available_years[0]
        return self.load_year_data(latest_year)

    def search_papers(self, keyword: str, search_fields: List[str] = None) -> List[tuple]:
        """
        搜索论文

        Args:
            keyword: 搜索关键词
            search_fields: 搜索字段，默认搜索标题和摘要

        Returns:
            搜索结果列表 [(category, paper), ...]
        """
        if search_fields is None:
            search_fields = ['title', 'abstract']

        keyword_lower = keyword.lower()
        results = []

        for category, paper in self.all_papers:
            for field in search_fields:
                if field == 'title':
                    if keyword_lower in paper.title.lower():
                        results.append((category, paper))
                        break
                elif field == 'abstract':
                    if keyword_lower in paper.abstract.lower():
                        results.append((category, paper))
                        break
                elif field == 'authors' and paper.authors:
                    if any(keyword_lower in author.lower() for author in paper.authors):
                        results.append((category, paper))
                        break

        return results

    def get_category_stats(self) -> Dict[str, Any]:
        """获取分类统计信息"""
        stats = {
            'total_categories': len(self.categories),
            'total_papers': len(self.all_papers),
            'categories': []
        }

        for cat_name, cat_data in self.categories.items():
            stats['categories'].append({
                'name': cat_name,
                'count': cat_data['count'],
                'summary': cat_data['summary'] 
            })

        return stats


# 全局可视化器实例
visualizer = None

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能体强化学习</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5em;
        }

        .stats {
            display: flex;
            gap: 30px;
            margin-top: 20px;
            flex-wrap: wrap;
        }

        .stat-item {
            flex: 1;
            min-width: 150px;
            text-align: center;
        }

        .stat-number {
            font-size: 2em;
            color: #667eea;
            font-weight: bold;
        }

        .stat-label {
            color: #666;
            margin-top: 5px;
        }

        .search-section {
            background: white;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .search-container {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .search-input {
            flex: 1;
            min-width: 200px;
            padding: 12px 15px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 1em;
            transition: border-color 0.3s;
        }

        .search-input:focus {
            outline: none;
            border-color: #667eea;
        }

        .search-btn {
            padding: 12px 30px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 1em;
            cursor: pointer;
            transition: background 0.3s;
        }

        .search-btn:hover {
            background: #5568d3;
        }

        .clear-btn {
            padding: 12px 30px;
            background: #999;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 1em;
            cursor: pointer;
            transition: background 0.3s;
        }

        .clear-btn:hover {
            background: #777;
        }

        .search-fields {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }

        .search-field {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .search-field input[type="checkbox"] {
            cursor: pointer;
        }

        .search-field label {
            cursor: pointer;
        }

        .categories-section {
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .category-card {
            border: 1px solid #eee;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
            transition: transform 0.3s, box-shadow 0.3s;
        }

        .category-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
        }

        .category-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .category-title {
            font-size: 1.3em;
            font-weight: bold;
        }

        .category-count {
            background: rgba(255, 255, 255, 0.3);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }

        .category-content {
            padding: 20px;
            max-height: 1500px;
            overflow-y: auto;
            overflow-x: hidden;
            transition: max-height 0.3s;
        }

        .category-content.collapsed {
            max-height: 0;
            padding: 0 20px;
            overflow: hidden;
        }

        /* 美化滚动条 */
        .category-content::-webkit-scrollbar {
            width: 8px;
        }

        .category-content::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }

        .category-content::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }

        .category-content::-webkit-scrollbar-thumb:hover {
            background: #5568d3;
        }

        /* Firefox 滚动条 */
        .category-content {
            scrollbar-color: #667eea #f1f1f1;
            scrollbar-width: thin;
        }

        .category-summary {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            line-height: 1.6;
            color: #555;
        }

        .papers-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            animation: fadeIn 0.3s ease-in;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .pagination {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }

        .pagination-btn {
            padding: 8px 12px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9em;
        }

        .pagination-btn:hover {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .pagination-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .pagination-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .pagination-info {
            font-size: 0.85em;
            color: #666;
            align-self: center;
        }

        .papers-count {
            font-size: 0.85em;
            color: #999;
            margin-top: 10px;
            text-align: center;
        }

        .paper-card {
            background: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .paper-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }

        .paper-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            line-height: 1.4;
        }

        .paper-venue {
            display: inline-block;
            background: #e8eaf6;
            color: #667eea;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            margin-bottom: 10px;
        }

        .paper-abstract {
            color: #666;
            font-size: 0.9em;
            line-height: 1.5;
            margin-bottom: 12px;
            max-height: 100px;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .paper-links {
            display: flex;
            gap: 10px;
            margin-top: 12px;
            flex-wrap: wrap;
        }

        .paper-link {
            display: inline-block;
            padding: 6px 12px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.85em;
            transition: background 0.2s;
        }

        .paper-link:hover {
            background: #5568d3;
        }

        .paper-link.disabled {
            background: #ccc;
            cursor: not-allowed;
            text-decoration: line-through;
        }

        .search-results-info {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            color: #1976d2;
        }

        .no-results {
            text-align: center;
            padding: 40px;
            color: #999;
        }

        .toggle-icon {
            font-size: 1.2em;
        }

        .year-selector {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }

        .year-label {
            font-weight: 600;
            color: #333;
            font-size: 1.1em;
        }

        .year-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .year-btn {
            padding: 10px 16px;
            border: 2px solid #ddd;
            background: white;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 0.95em;
            font-weight: 500;
            color: #333;
        }

        .year-btn:hover {
            border-color: #667eea;
            color: #667eea;
        }

        .year-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
        }

        @media (max-width: 768px) {
            .header {
                padding: 20px;
            }

            .header h1 {
                font-size: 1.8em;
            }

            .year-selector {
                flex-direction: column;
                align-items: flex-start;
            }

            .year-buttons {
                width: 100%;
            }

            .stats {
                flex-direction: column;
                gap: 15px;
            }

            .search-container {
                flex-direction: column;
            }

            .papers-list {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 论文分类可视化与搜索</h1>
            <div class="year-selector">
                <span class="year-label">📅 选择年份:</span>
                <div class="year-buttons" id="yearButtons"></div>
            </div>
            <div class="stats" id="stats"></div>
        </div>

        <div class="search-section">
            <h2 style="margin-bottom: 20px;">🔍 搜索论文</h2>
            <div class="search-container">
                <input type="text" class="search-input" id="searchInput" placeholder="输入关键词搜索（标题、摘要、作者）...">
                <button class="search-btn" onclick="performSearch()">搜索</button>
                <button class="clear-btn" onclick="clearSearch()">清除搜索</button>
            </div>
            <div class="search-fields">
                <div class="search-field">
                    <input type="checkbox" id="searchTitle" checked>
                    <label for="searchTitle">标题</label>
                </div>
                <div class="search-field">
                    <input type="checkbox" id="searchAbstract" checked>
                    <label for="searchAbstract">摘要</label>
                </div>
                <div class="search-field">
                    <input type="checkbox" id="searchAuthors">
                    <label for="searchAuthors">作者</label>
                </div>
            </div>
        </div>

        <div class="categories-section">
            <div id="categoriesContainer"></div>
        </div>
    </div>

    <script>
        let allCategories = {};
        let searchMode = false;
        let searchResults = {};
        const PAPERS_PER_PAGE = 6; // 每页显示6篇论文
        let currentPage = {}; // 存储每个分类的当前页码
        let availableYears = []; // 可用的年份列表
        let currentYear = null; // 当前选中的年份

        // 页面加载时初始化
        window.addEventListener('load', () => {
            loadYears();
            loadCategories();
            loadStats();
        });

        function loadYears() {
            fetch('/api/years')
                .then(r => r.json())
                .then(data => {
                    availableYears = data.years;
                    currentYear = data.current_year;
                    renderYearButtons();
                });
        }

        function renderYearButtons() {
            const buttonsContainer = document.getElementById('yearButtons');
            let html = '';

            for (const year of availableYears) {
                const isActive = year === currentYear;
                html += `
                    <button class="year-btn ${isActive ? 'active' : ''}"
                            onclick="selectYear('${year}')"
                            title="查看 ${year} 年的论文">
                        ${year} 年
                    </button>
                `;
            }

            buttonsContainer.innerHTML = html;
        }

        function selectYear(year) {
            if (year === currentYear) {
                return; // 已经是当前年份，不需要切换
            }

            // 显示加载状态
            document.getElementById('yearButtons').innerHTML = '<span style="color: #667eea;">加载中...</span>';

            // 调用API加载该年份的数据
            fetch(`/api/load-year/${year}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        currentYear = year;
                        currentPage = {}; // 重置分页
                        loadYears(); // 重新加载年份按钮
                        loadCategories(); // 重新加载分类
                        loadStats(); // 重新加载统计
                        clearSearch(); // 清除搜索
                    } else {
                        alert(`加载失败: ${data.message}`);
                        loadYears(); // 恢复按钮
                    }
                })
                .catch(err => {
                    console.error('加载年份数据失败:', err);
                    alert('加载失败，请重试');
                    loadYears(); // 恢复按钮
                });
        }

        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    const statsHtml = `
                        <div class="stat-item">
                            <div class="stat-number">${data.total_papers}</div>
                            <div class="stat-label">论文总数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">${data.total_categories}</div>
                            <div class="stat-label">分类数量</div>
                        </div>
                    `;
                    document.getElementById('stats').innerHTML = statsHtml;
                });
        }

        function loadCategories() {
            fetch('/api/categories')
                .then(r => r.json())
                .then(data => {
                    allCategories = data;
                    renderCategories(data);
                });
        }

        function renderCategories(categories) {
            let html = '';
            if (Object.keys(categories).length === 0) {
                html = '<div class="no-results">暂无分类数据</div>';
            } else {
                for (const [catName, catData] of Object.entries(categories)) {
                    currentPage[catName] = 1; // 初始化每个分类的当前页码
                    html += renderCategoryCard(catName, catData);
                }
            }
            document.getElementById('categoriesContainer').innerHTML = html;

            // 为所有分类卡片添加点击事件
            document.querySelectorAll('.category-header').forEach(header => {
                header.addEventListener('click', (e) => {
                    const content = header.nextElementSibling;
                    content.classList.toggle('collapsed');
                    const icon = header.querySelector('.toggle-icon');
                    icon.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
                });
            });
        }

        function renderCategoryCard(catName, catData) {
            const totalPapers = catData.papers.length;
            const totalPages = Math.ceil(totalPapers / PAPERS_PER_PAGE);
            currentPage[catName] = currentPage[catName] || 1;

            // 获取当前页的论文
            const startIdx = (currentPage[catName] - 1) * PAPERS_PER_PAGE;
            const endIdx = startIdx + PAPERS_PER_PAGE;
            const currentPapers = catData.papers.slice(startIdx, endIdx);

            const papersHtml = currentPapers
                .map(paper => `
                    <div class="paper-card">
                        <div class="paper-title">${paper.title}</div>
                        <div class="paper-venue">${paper.venue}</div>
                        <div class="paper-abstract">${paper.abstract}</div>
                        <div class="paper-links">
                            ${paper.forum_url ? `<a href="${paper.forum_url}" target="_blank" class="paper-link">📄 论文</a>` : ''}
                            ${paper.pdf_url ? `<a href="${paper.pdf_url}" target="_blank" class="paper-link">PDF</a>` : ''}
                        </div>
                    </div>
                `)
                .join('');

            // 生成分页按钮
            let paginationHtml = '';
            if (totalPages > 1) {
                paginationHtml = `
                    <div class="pagination">
                        <button class="pagination-btn" onclick="changePage('${catName}', 1)" ${currentPage[catName] === 1 ? 'disabled' : ''}>首页</button>
                        <button class="pagination-btn" onclick="changePage('${catName}', ${currentPage[catName] - 1})" ${currentPage[catName] === 1 ? 'disabled' : ''}>上一页</button>
                        <span class="pagination-info">第 ${currentPage[catName]} / ${totalPages} 页</span>
                        <button class="pagination-btn" onclick="changePage('${catName}', ${currentPage[catName] + 1})" ${currentPage[catName] === totalPages ? 'disabled' : ''}>下一页</button>
                        <button class="pagination-btn" onclick="changePage('${catName}', ${totalPages})" ${currentPage[catName] === totalPages ? 'disabled' : ''}>末页</button>
                    </div>
                    <div class="papers-count">显示 ${startIdx + 1}-${Math.min(endIdx, totalPapers)} / 共 ${totalPapers} 篇论文</div>
                `;
            }

            return `
                <div class="category-card">
                    <div class="category-header">
                        <span class="category-title">${catName}</span>
                        <span class="category-count">
                            <span class="toggle-icon">▼</span>
                            ${catData.count} 篇
                        </span>
                    </div>
                    <div class="category-content">
                        ${catData.summary ? `<div class="category-summary">${catData.summary}</div>` : ''}
                        <div class="papers-list">
                            ${papersHtml}
                        </div>
                        ${paginationHtml}
                    </div>
                </div>
            `;
        }

        function changePage(catName, pageNum) {
            // 更新当前页码
            const totalPages = Math.ceil(allCategories[catName].papers.length / PAPERS_PER_PAGE);
            if (pageNum >= 1 && pageNum <= totalPages) {
                currentPage[catName] = pageNum;

                // 重新渲染该分类的卡片
                const categoryCard = document.querySelector(`[data-category="${catName}"]`);
                if (categoryCard) {
                    categoryCard.innerHTML = renderCategoryCard(catName, allCategories[catName]);
                } else {
                    // 如果找不到，重新渲染整个分类
                    const allHtml = [];
                    for (const [name, data] of Object.entries(allCategories)) {
                        allHtml.push(renderCategoryCard(name, data));
                    }
                    document.getElementById('categoriesContainer').innerHTML = allHtml.join('');
                }

                // 重新绑定事件
                document.querySelectorAll('.category-header').forEach(header => {
                    header.addEventListener('click', (e) => {
                        const content = header.nextElementSibling;
                        content.classList.toggle('collapsed');
                        const icon = header.querySelector('.toggle-icon');
                        icon.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
                    });
                });
            }
        }

        function performSearch() {
            const keyword = document.getElementById('searchInput').value.trim();
            if (!keyword) {
                clearSearch();
                return;
            }

            const fields = [];
            if (document.getElementById('searchTitle').checked) fields.push('title');
            if (document.getElementById('searchAbstract').checked) fields.push('abstract');
            if (document.getElementById('searchAuthors').checked) fields.push('authors');

            fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keyword, fields })
            })
                .then(r => r.json())
                .then(data => {
                    searchMode = true;
                    searchResults = data;
                    renderSearchResults(data, keyword);
                });
        }

        function renderSearchResults(results, keyword) {
            let html = `<div class="search-results-info">🔍 搜索结果：找到 <strong>${results.total_results}</strong> 条相关论文</div>`;

            if (results.total_results === 0) {
                html += '<div class="no-results">未找到相关论文</div>';
            } else {
                for (const [catName, papers] of Object.entries(results.results)) {
                    const searchCatName = `search_${catName}`;
                    const totalPapers = papers.length;
                    const totalPages = Math.ceil(totalPapers / PAPERS_PER_PAGE);
                    currentPage[searchCatName] = currentPage[searchCatName] || 1;

                    // 获取当前页的论文
                    const startIdx = (currentPage[searchCatName] - 1) * PAPERS_PER_PAGE;
                    const endIdx = startIdx + PAPERS_PER_PAGE;
                    const currentPapers = papers.slice(startIdx, endIdx);

                    // 生成分页按钮
                    let paginationHtml = '';
                    if (totalPages > 1) {
                        paginationHtml = `
                            <div class="pagination">
                                <button class="pagination-btn" onclick="changeSearchPage('${catName}', 1)" ${currentPage[searchCatName] === 1 ? 'disabled' : ''}>首页</button>
                                <button class="pagination-btn" onclick="changeSearchPage('${catName}', ${currentPage[searchCatName] - 1})" ${currentPage[searchCatName] === 1 ? 'disabled' : ''}>上一页</button>
                                <span class="pagination-info">第 ${currentPage[searchCatName]} / ${totalPages} 页</span>
                                <button class="pagination-btn" onclick="changeSearchPage('${catName}', ${currentPage[searchCatName] + 1})" ${currentPage[searchCatName] === totalPages ? 'disabled' : ''}>下一页</button>
                                <button class="pagination-btn" onclick="changeSearchPage('${catName}', ${totalPages})" ${currentPage[searchCatName] === totalPages ? 'disabled' : ''}>末页</button>
                            </div>
                            <div class="papers-count">显示 ${startIdx + 1}-${Math.min(endIdx, totalPapers)} / 共 ${totalPapers} 篇论文</div>
                        `;
                    }

                    html += `
                        <div class="category-card">
                            <div class="category-header" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                                <span class="category-title">${catName}</span>
                                <span class="category-count">
                                    <span class="toggle-icon">▼</span>
                                    ${papers.length} 篇
                                </span>
                            </div>
                            <div class="category-content">
                                <div class="papers-list">
                                    ${currentPapers.map(paper => `
                                        <div class="paper-card">
                                            <div class="paper-title">${paper.title}</div>
                                            <div class="paper-venue">${paper.venue}</div>
                                            <div class="paper-abstract">${paper.abstract}</div>
                                            <div class="paper-links">
                                                ${paper.forum_url ? `<a href="${paper.forum_url}" target="_blank" class="paper-link">📄 论文</a>` : ''}
                                                ${paper.pdf_url ? `<a href="${paper.pdf_url}" target="_blank" class="paper-link">PDF</a>` : ''}
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                                ${paginationHtml}
                            </div>
                        </div>
                    `;
                }
            }

            document.getElementById('categoriesContainer').innerHTML = html;

            // 为搜索结果的分类卡片添加点击事件
            document.querySelectorAll('.category-header').forEach(header => {
                header.addEventListener('click', (e) => {
                    const content = header.nextElementSibling;
                    content.classList.toggle('collapsed');
                    const icon = header.querySelector('.toggle-icon');
                    icon.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
                });
            });
        }

        function changeSearchPage(catName, pageNum) {
            // 更新当前页码
            const searchCatName = `search_${catName}`;
            const papers = searchResults.results[catName] || [];
            const totalPages = Math.ceil(papers.length / PAPERS_PER_PAGE);

            if (pageNum >= 1 && pageNum <= totalPages) {
                currentPage[searchCatName] = pageNum;

                // 重新渲染搜索结果
                renderSearchResults(searchResults, document.getElementById('searchInput').value);
            }
        }

        function clearSearch() {
            document.getElementById('searchInput').value = '';
            searchMode = false;
            currentPage = {}; // 重置页码
            loadCategories();
        }
    </script>
</body>
</html>
"""


def create_app() -> Flask:
    """创建Flask应用"""
    app = Flask(__name__)

    @app.route('/')
    def index():
        """主页"""
        return render_template_string(HTML_TEMPLATE)

    @app.route('/api/years')
    def api_years():
        """获取可用的年份列表"""
        return jsonify({
            'years': visualizer.available_years,
            'current_year': visualizer.current_year
        })

    @app.route('/api/load-year/<year>', methods=['POST'])
    def api_load_year(year: str):
        """加载特定年份的数据"""
        if visualizer.load_year_data(year):
            return jsonify({
                'success': True,
                'year': year,
                'message': f'成功加载 {year} 年的数据'
            })
        else:
            return jsonify({
                'success': False,
                'year': year,
                'message': f'加载 {year} 年的数据失败'
            }), 400

    @app.route('/api/stats')
    def api_stats():
        """获取统计信息"""
        stats = visualizer.get_category_stats()
        return jsonify(stats)

    @app.route('/api/categories')
    def api_categories():
        """获取所有分类"""
        result = {}
        for cat_name, cat_data in visualizer.categories.items():
            result[cat_name] = {
                'count': cat_data['count'],
                'summary': cat_data['summary'],
                'papers': [
                    {
                        'title': paper.title,
                        'abstract': paper.abstract,
                        'venue': paper.venue,
                        'paper_id': paper.paper_id,
                        'authors': paper.authors or [],
                        'pdf_url': paper.pdf_url,
                        'forum_url': paper.forum_url
                    }
                    for paper in cat_data['papers']
                ]
            }
        return jsonify(result)

    @app.route('/api/search', methods=['POST'])
    def api_search():
        """搜索论文"""
        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        fields = data.get('fields', ['title', 'abstract'])

        if not keyword:
            return jsonify({'total_results': 0, 'results': {}})

        search_results = visualizer.search_papers(keyword, fields)

        # 按分类整理结果
        results_by_category = {}
        for category, paper in search_results:
            if category not in results_by_category:
                results_by_category[category] = []
            results_by_category[category].append({
                'title': paper.title,
                'abstract': paper.abstract,
                'venue': paper.venue,
                'paper_id': paper.paper_id,
                'authors': paper.authors or [],
                'pdf_url': paper.pdf_url,
                'forum_url': paper.forum_url
            })

        return jsonify({
            'total_results': len(search_results),
            'results': results_by_category
        })

    return app


def find_available_port(start_port=5000, max_attempts=10):
    """找到可用的端口"""
    import socket

    for port in range(start_port, start_port + max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result != 0:  # 端口未被占用
                return port
        except:
            return port

    return None


def main():
    """主函数"""
    global visualizer

    print("\n" + "=" * 60)
    print("论文分类可视化与搜索系统")
    print("=" * 60)

    # 获取输出目录
    base_dir = Path(__file__).parent.parent
    output_dir = base_dir / 'output'

    if not output_dir.exists():
        print(f"错误: 输出目录不存在: {output_dir}")
        print("请先运行 paper_search_classify.py 进行论文分类")
        return

    # 初始化可视化器
    visualizer = ClassificationVisualizer(str(output_dir))

    # 尝试自动加载最新的分类结果
    if not visualizer.load_classification_results():
        print("请指定分类结果所在的目录路径")
        result_path = input("请输入结果目录路径 (或按Enter自动选择最新): ").strip()
        if result_path:
            if not visualizer.load_classification_results(result_path):
                print("加载失败")
                return
        else:
            print("加载失败")
            return

    # 创建Flask应用
    app = create_app()

    # 启动Web服务
    print("\n✓ 数据加载成功！")
    print("\n正在启动Web服务...")

    # 找到可用端口
    port = find_available_port(5000)
    if not port:
        print("错误: 无法找到可用的端口")
        return

    host = '127.0.0.1'
    url = f"http://{host}:{port}"

    print("=" * 60)
    print(f"📊 打开浏览器访问: {url}")
    print("=" * 60)
    print("\n按 Ctrl+C 停止服务\n")

    try:
        # 禁用Flask的日志输出（减少干扰）
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("\n\n服务已停止")
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print("\n💡 解决方案:")
        print("1. 尝试以管理员身份运行本程序")
        print("2. 检查防火墙设置是否阻止了Python")
        print("3. 关闭占用该端口的其他程序")
        print("4. 修改端口号重试")
        return


if __name__ == '__main__':
    main()
