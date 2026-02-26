"""Token 池管理"""

import random
import time
from typing import Dict, List, Optional, Iterator

from app.services.token.models import TokenInfo, TokenStatus, TokenPoolStats


def _active_inflight(token: TokenInfo, now_ms: int) -> int:
    """Count active inflight reservations, pruning expired entries."""
    m = token.inflight_map
    if not m:
        return 0
    stale = [k for k, v in m.items() if v <= now_ms]
    for k in stale:
        del m[k]
    return len(m)


class TokenPool:
    """Token 池（管理一组 Token）"""

    def __init__(self, name: str):
        self.name = name
        self._tokens: Dict[str, TokenInfo] = {}

    def add(self, token: TokenInfo):
        """添加 Token"""
        self._tokens[token.token] = token

    def remove(self, token_str: str) -> bool:
        """删除 Token"""
        if token_str in self._tokens:
            del self._tokens[token_str]
            return True
        return False

    def get(self, token_str: str) -> Optional[TokenInfo]:
        """获取 Token"""
        return self._tokens.get(token_str)

    def select(
        self,
        bucket: str = "normal",
        exclude: Optional[set] = None,
        now_ms: Optional[int] = None,
        max_concurrent: int = 0,
    ) -> Optional[TokenInfo]:
        """
        选择一个可用 Token
        策略:
        1. 选择 active 状态且有配额的 token
        2. 过滤超出并发上限的 token (max_concurrent <= 0 时不限)
        3. 优先选择剩余额度最多的
        4. 额度相同时优先选择 inflight 最少的
        5. 都相同则随机选择
        """
        _exclude = exclude or set()
        _now_ms = int(now_ms if now_ms is not None else (time.time() * 1000))

        if bucket == "heavy":
            available = [
                t
                for t in self._tokens.values()
                if t.status in (TokenStatus.ACTIVE, TokenStatus.COOLING)
                and t.heavy_quota != 0
                and (max_concurrent <= 0 or _active_inflight(t, _now_ms) < max_concurrent)
                and t.token not in _exclude
            ]

            if not available:
                return None

            unknown = [t for t in available if t.heavy_quota < 0]
            if unknown:
                # Prefer least-loaded among unknown-quota tokens
                min_load = min(_active_inflight(t, _now_ms) for t in unknown)
                best = [t for t in unknown if _active_inflight(t, _now_ms) == min_load]
                return random.choice(best)

            max_quota = max(t.heavy_quota for t in available)
            candidates = [t for t in available if t.heavy_quota == max_quota]
            min_load = min(_active_inflight(t, _now_ms) for t in candidates)
            best = [t for t in candidates if _active_inflight(t, _now_ms) == min_load]
            return random.choice(best)

        available = [
            t for t in self._tokens.values()
            if t.status == TokenStatus.ACTIVE and t.quota > 0
            and (max_concurrent <= 0 or _active_inflight(t, _now_ms) < max_concurrent)
            and t.token not in _exclude
        ]

        if not available:
            return None

        # 找到最大额度
        max_quota = max(t.quota for t in available)

        # 筛选最大额度
        candidates = [t for t in available if t.quota == max_quota]

        # 额度相同时，优先选择 inflight 最少的
        min_load = min(_active_inflight(t, _now_ms) for t in candidates)
        best = [t for t in candidates if _active_inflight(t, _now_ms) == min_load]

        return random.choice(best)

    def count(self) -> int:
        """Token 数量"""
        return len(self._tokens)

    def list(self) -> List[TokenInfo]:
        """获取所有 Token"""
        return list(self._tokens.values())

    def get_stats(self) -> TokenPoolStats:
        """获取池统计信息"""
        stats = TokenPoolStats(total=len(self._tokens))

        for token in self._tokens.values():
            stats.total_quota += token.quota

            if token.status == TokenStatus.ACTIVE:
                stats.active += 1
            elif token.status == TokenStatus.DISABLED:
                stats.disabled += 1
            elif token.status == TokenStatus.EXPIRED:
                stats.expired += 1
            elif token.status == TokenStatus.COOLING:
                stats.cooling += 1

        if stats.total > 0:
            stats.avg_quota = stats.total_quota / stats.total

        return stats

    def __iter__(self) -> Iterator[TokenInfo]:
        return iter(self._tokens.values())


__all__ = ["TokenPool"]
