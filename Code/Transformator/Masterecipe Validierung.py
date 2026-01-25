#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
from urllib.parse import urlparse
from lxml import etree


class LocalResolver(etree.Resolver):
    """
    让 XSD 里的 xsd:include / xsd:import 能从本地目录解析。
    - 对相对路径：按“当前正在解析的 XSD 文件所在目录”拼接
    - 对 file:/// 绝对路径：直接读取
    """
    def resolve(self, url, pubid, context):
        # url 可能是 "B2MML-CoreComponents.xsd" 或 "file:///.../xxx.xsd"
        parsed = urlparse(url)

        # 1) file:///...
        if parsed.scheme == "file":
            path = os.path.abspath(os.path.join(parsed.netloc, parsed.path))
            if os.path.exists(path):
                return self.resolve_filename(path, context)
            return None

        # 2) 相对路径：基于当前 XSD 文件目录
        base = context.url  # 当前正在解析的文档 url（通常是一个文件路径）
        base_dir = os.path.dirname(base) if base else os.getcwd()
        candidate = os.path.abspath(os.path.join(base_dir, url))

        if os.path.exists(candidate):
            return self.resolve_filename(candidate, context)

        # 找不到就交给默认机制（可能会失败，但错误信息更明确）
        return None


def validate(xml_path: str, xsd_path: str) -> int:
    xml_path = os.path.abspath(xml_path)
    xsd_path = os.path.abspath(xsd_path)

    if not os.path.exists(xml_path):
        print(f"[ERROR] XML not found: {xml_path}")
        return 2
    if not os.path.exists(xsd_path):
        print(f"[ERROR] XSD not found: {xsd_path}")
        return 2

    parser = etree.XMLParser(
        load_dtd=False,
        no_network=True,   # 禁止网络加载（更安全、更可控）
        remove_comments=False,
        resolve_entities=False
    )
    parser.resolvers.add(LocalResolver())

    # 解析 XSD 并构建 schema
    try:
        xsd_doc = etree.parse(xsd_path, parser)
        schema = etree.XMLSchema(xsd_doc)
    except (etree.XMLSchemaParseError, etree.XMLSyntaxError, OSError) as e:
        print("[ERROR] Failed to parse/compile XSD schema.")
        print(f"        XSD: {xsd_path}")
        print(f"        Detail: {e}")
        return 3

    # 解析 XML 并验证
    try:
        xml_doc = etree.parse(xml_path, parser)
    except (etree.XMLSyntaxError, OSError) as e:
        print("[ERROR] XML is not well-formed (syntax error).")
        print(f"        XML: {xml_path}")
        print(f"        Detail: {e}")
        return 4

    ok = schema.validate(xml_doc)
    if ok:
        print("✅ VALID: XML conforms to the XSD.")
        return 0

    print("❌ INVALID: XML does NOT conform to the XSD.")
    # 输出详细错误（包含行号/列号/信息）
    for i, err in enumerate(schema.error_log, start=1):
        # err.domain_name / err.type_name 也可以输出，但通常 message 就够了
        print(f"{i:02d}) line {err.line}, col {err.column}: {err.message}")
        if i >= 50:
            print("... (more errors omitted)")
            break

    return 1


def main():
    ap = argparse.ArgumentParser(
        description="Validate a B2MML MasterRecipe XML against AllSchemas.xsd (supports local includes/imports)."
    )
    ap.add_argument("--xml", required=True, help="Path to MasterRecipe XML, e.g. MasterRecipe_B2MML.xml")
    ap.add_argument("--xsd", required=True, help="Path to AllSchemas.xsd")
    args = ap.parse_args()

    code = validate(args.xml, args.xsd)
    sys.exit(code)


if __name__ == "__main__":
    main()
