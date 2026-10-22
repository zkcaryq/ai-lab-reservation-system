"""手动验证文字和图文是否都能生成1024维融合向量。"""

import argparse
import asyncio
from pathlib import Path

from app.services.knowledge.bailian_embedding_services import create_fused_embedding


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()

    # 先验证纯文字输入。
    text_vector = await create_fused_embedding(
        text="人工智能实验室位于科技楼A区101，可容纳40人。",
    )
    print(f"纯文字融合向量维度：{len(text_vector)}")

    # 传入--image时，再验证图片和文字融合输入。
    if args.image is not None:
        image_vector = await create_fused_embedding(
            text="实验室平面图，包含设备区、紧急出口和疏散方向。",
            image_path=args.image,
        )
        print(f"图文融合向量维度：{len(image_vector)}")


if __name__ == "__main__":
    asyncio.run(main())
