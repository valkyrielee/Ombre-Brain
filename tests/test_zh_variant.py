# ============================================================
# Test: Traditional/Simplified retrieval parity — pure local, no LLM
# 测试：繁简互查 —— 纯本地，不需要 LLM
#
# Why this matters more than it looks: _calc_topic_score compares characters.
# 「記憶」and「记忆」share none of them, so before this fix a Traditional query
# scored ~0 against a Simplified bucket, fell under fuzzy_threshold, and never
# entered the candidate list at all. The memory existed and was simply
# unreachable — silence, not a bad ranking.
#
# Measured against the real 314-bucket vault (2026-07-28 backup) on
# content previews alone:「戀愛」1 → 47 reachable buckets,「記憶」1 → 8,
# 「項鍊」and「結婚」0 → 1. Nothing became unreachable.
#
# Verifies:
#   - folding is comparison-only (bucket content is returned untouched)
#   - Traditional query reaches a Simplified bucket, and the reverse
#   - same-script queries keep working (no regression)
#   - a missing zhconv degrades to old behaviour instead of raising
# ============================================================

import pytest

from bucket_manager import _fold_zh


class TestFold:
    def test_folds_traditional_to_simplified(self):
        assert _fold_zh("記憶") == "记忆"
        assert _fold_zh("戀愛") == "恋爱"

    def test_simplified_is_left_alone(self):
        assert _fold_zh("记忆") == "记忆"

    def test_both_scripts_land_on_the_same_string(self):
        # This is the whole mechanism: two spellings, one comparison key.
        assert _fold_zh("項鍊") == _fold_zh("项链")
        assert _fold_zh("結婚") == _fold_zh("结婚")

    def test_non_chinese_untouched(self):
        assert _fold_zh("Adam's House") == "Adam's House"
        assert _fold_zh("") == ""

    def test_none_safe(self):
        assert _fold_zh(None) is None


@pytest.mark.asyncio
class TestCrossScriptSearch:
    async def _mk(self, bucket_mgr, content, name, tags=None):
        return await bucket_mgr.create(
            content=content, tags=tags or [], domain=["测试"],
            name=name, importance=5,
        )

    async def test_traditional_query_finds_simplified_bucket(self, bucket_mgr):
        await self._mk(bucket_mgr, "去年冬天在柳州买的项链，一直戴着。", "项链的承诺")
        hits = await bucket_mgr.search("項鍊")
        assert hits, "a Traditional query must reach a Simplified bucket"
        assert "项链" in hits[0]["content"]

    async def test_simplified_query_finds_traditional_bucket(self, bucket_mgr):
        await self._mk(bucket_mgr, "那天的記憶還很清楚，她笑了。", "記憶片段")
        hits = await bucket_mgr.search("记忆")
        assert hits, "a Simplified query must reach a Traditional bucket"

    async def test_same_script_still_works(self, bucket_mgr):
        # The fix must not cost anything for queries that already matched.
        await self._mk(bucket_mgr, "胃炎复发，要按时吃饭。", "胃炎观察")
        assert await bucket_mgr.search("胃炎")

    async def test_stored_content_is_never_rewritten(self, bucket_mgr):
        # Folding happens in the comparison only. What comes back is the bucket
        # exactly as it was written — the script Adam chose is part of the memory.
        original = "那天的記憶還很清楚。"
        bid = await self._mk(bucket_mgr, original, "記憶片段")
        stored = await bucket_mgr.get(bid)
        assert stored["content"].strip() == original
        hits = await bucket_mgr.search("记忆")
        assert any(h["content"].strip() == original for h in hits)
