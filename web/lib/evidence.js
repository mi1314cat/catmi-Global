// lib/evidence.js — Evidence 统一模型 JS 侧 (P0-1) — 与 news/evidence_model.py 字段一一对应
// 纯映射层: MCP search_events/get_event/search 结果统一为 Evidence 形状; 零新存储
'use strict';

const EXCERPT_CHARS = 300;

// s 可为 sources 行(含 name/source_type/tier/quality_score/verification_status)或 null
function toEvidence(a, s) {
  const content = a.content || '';
  const summary = a.summary_text || '';
  return {
    id: a.id, article_id: a.id, story_id: a.story_id || null,
    url: a.url || '', canonical_url: a.canonical_url || a.url || '',
    title: a.title || a.original_title || '',
    author: a.author || null,
    source_id: a.source_id || null,
    source: (s && s.name) || a.source || null,
    source_type: (s && s.source_type) || a.source_type || null,
    tier: (s && s.tier) || a.tier || null,
    quality_score: (s && s.quality_score != null ? s.quality_score : a.quality_score) ?? null,
    verification_status: (s && s.verification_status) || a.verification_status || null,
    published_at: a.published_at || null,            // 发布时间 — 不用 fetched_at 冒充
    published_at_source: a.published_at ? 'article.published_at' : null,
    retrieved_at: a.fetched_at || null,              // 抓取时间
    discovered_at: a.discovered_at || null,
    language: a.language || null,
    content_chars: content ? content.length : 0,
    excerpt: (summary || content).slice(0, EXCERPT_CHARS),
    extract_method: a.extract_method || null,
    dupe_of: a.dupe_of || null,
    // 评分字段 (P0-3/P0-6 填充)
    relevance_score: null, freshness_score: null,
    source_quality_score: (s && s.quality_score) ?? a.quality_score ?? null,
    final_score: null, original_reporting: null, independent_source: null,
  };
}

module.exports = { toEvidence, EXCERPT_CHARS };
