"""Protege os limites de responsabilidade solicitados para a API."""

import ast
from pathlib import Path
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_routes_only_delegate_and_use_response_schemas(self):
        for path in Path("src/routers").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in tree.body:
                if (
                    not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    or not node.decorator_list
                ):
                    continue
                self.assertEqual(len(node.body), 1, path)
                self.assertIsInstance(node.body[0], ast.Return, path)
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        keywords = {
                            keyword.arg: keyword.value for keyword in decorator.keywords
                        }
                        if not (
                            isinstance(keywords.get("status_code"), ast.Constant)
                            and keywords["status_code"].value == 204
                        ):
                            self.assertIn("response_model", keywords, path)

    def test_sql_stays_in_services(self):
        for folder in ["routers", "controllers", "helpers"]:
            for path in Path("src", folder).glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                    if isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
                        self.fail(f"Construção SQL fora de services: {path}")
        for path in Path("src/services").glob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            self.assertNotIn("HTTPException", text, path)
            self.assertNotIn("src.controllers", text, path)
            self.assertNotIn("src.routers", text, path)
