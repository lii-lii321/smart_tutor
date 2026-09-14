"""导出 OpenAPI schema 供前端生成类型（npm run gen:api）。

openapi.json 是构建产物：不提交 git；生产 docs 已关闭（DEBUG=false），
类型生成只在开发机执行本脚本，不依赖运行中的服务。
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    path = pathlib.Path(__file__).resolve().parent.parent / "openapi.json"
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {path}")


if __name__ == "__main__":
    main()
