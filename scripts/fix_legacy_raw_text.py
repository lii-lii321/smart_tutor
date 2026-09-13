"""
一次性修复存量订单的 raw_text 混单问题（2026-09-13，用户反馈订单详情
"原始完整信息"显示整段多单文本）。

背景：旧版解析在多单粘贴时把整批文本存进了每一单的 raw_text；
新版 parser（extract_order_block）已按单号逐单截取，本脚本修复存量行。

逻辑：raw_text 含 ≥2 个订单标题行的，按本单 raw_id 数字截取自身块；
定位失败（标题行缺失/单号不在文本中）保持原样并报告。

用法：
  python scripts/fix_legacy_raw_text.py --url sqlite+aiosqlite:///./dev.db           # 预览
  python scripts/fix_legacy_raw_text.py --url ... --apply                            # 写库
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine

import models.domain  # noqa: F401
from models.domain import Order
from services.parser import _is_order_header_line, extract_order_block


def _header_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if _is_order_header_line(line))


async def main(url: str, apply: bool) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        rows = (await conn.execute(
            select(Order.id, Order.raw_id, Order.raw_text)
        )).all()

        fixable: list[tuple[int, str]] = []
        not_located: list[tuple[int, str]] = []
        for order_id, raw_id, raw_text in rows:
            if not raw_text or _header_count(raw_text) < 2:
                continue
            block = extract_order_block(raw_text, raw_id)
            if block and block != raw_text.strip():
                fixable.append((order_id, block))
            else:
                not_located.append((order_id, raw_id))

        print(f"扫描 {len(rows)} 单")
        print(f"可修复（多单混入且能按单号定位到自身块）：{len(fixable)} 单")
        for order_id, block in fixable[:5]:
            preview = block.replace("\n", " ")[:80]
            print(f"  - 订单 #{order_id}: {preview}...")
        print(f"定位失败（保持原样）：{len(not_located)} 单 -> {not_located[:10]}")

        if apply and fixable:
            for order_id, block in fixable:
                await conn.execute(
                    update(Order).where(Order.id == order_id).values(raw_text=block)
                )
            print(f"已写入 {len(fixable)} 单")
        elif not apply:
            print("（预览模式，未写库；加 --apply 生效）")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="修复存量订单 raw_text 混单")
    parser.add_argument("--url", required=True)
    parser.add_argument("--apply", action="store_true", help="实际写库（默认仅预览）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url, args.apply)))
