import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "src" / "notebooks").glob("*.ipynb"))


def load_notebook(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source(cell):
    value = cell.get("source", [])
    return value if isinstance(value, str) else "".join(value)


class NotebookPolicyTests(unittest.TestCase):
    def test_notebooks_exist(self):
        self.assertEqual(
            [path.name for path in NOTEBOOKS],
            ["05_monitoring_and_aiops.ipynb", "multilingual_warranty_qwen3_vs_labse.ipynb"],
        )

    def test_every_code_cell_has_explanatory_markdown_immediately_before_it(self):
        for path in NOTEBOOKS:
            cells = load_notebook(path)["cells"]
            self.assertEqual(cells[0]["cell_type"], "markdown", path.name)
            for index, cell in enumerate(cells):
                if cell["cell_type"] == "code":
                    self.assertGreater(index, 0, f"{path.name} cell {index}")
                    self.assertEqual(
                        cells[index - 1]["cell_type"],
                        "markdown",
                        f"{path.name} code cell {index} lacks preceding markdown",
                    )
                    self.assertTrue(source(cells[index - 1]).strip())

    def test_markdown_has_no_horizontal_rule(self):
        for path in NOTEBOOKS:
            for index, cell in enumerate(load_notebook(path)["cells"]):
                if cell["cell_type"] == "markdown":
                    self.assertNotRegex(
                        source(cell),
                        r"(?m)^\s*---\s*$",
                        f"{path.name} markdown cell {index}",
                    )

    def test_notebooks_use_widgets_not_custom_spark_configuration(self):
        for path in NOTEBOOKS:
            text = path.read_text(encoding="utf-8")
            self.assertIn('dbutils.widgets.text(\\"catalog\\"', text)
            self.assertIn('dbutils.widgets.text(\\"schema\\"', text)
            self.assertNotIn("spark.conf.set", text)


class DataContractTests(unittest.TestCase):
    def test_day2_uses_base_defect_id_contract(self):
        base = (ROOT / "src/notebooks/multilingual_warranty_qwen3_vs_labse.ipynb").read_text(
            encoding="utf-8"
        )
        day2 = (ROOT / "src/notebooks/05_monitoring_and_aiops.ipynb").read_text(
            encoding="utf-8"
        )
        self.assertIn('\\"defect_id\\"', base)
        self.assertIn('\\"defect_id\\"', day2)
        self.assertNotIn("defect_type", day2)

    def test_day2_scores_against_prior_batches(self):
        day2 = (ROOT / "src/notebooks/05_monitoring_and_aiops.ipynb").read_text(
            encoding="utf-8"
        )
        self.assertIn('emb_df[emb_df[\\"batch_date\\"] < batch_date]', day2)
        self.assertNotIn("mlflow.pyfunc.PythonModel()", day2)

    def test_dependency_and_model_revision_are_pinned(self):
        base = (ROOT / "src/notebooks/multilingual_warranty_qwen3_vs_labse.ipynb").read_text(
            encoding="utf-8"
        )
        self.assertIn("sentence-transformers==5.1.1", base)
        self.assertIn("scikit-learn==1.7.2", base)
        self.assertRegex(base, r"836121a0533e5664b21c7aacc5d22951f2b8b25b")


class RepositoryContractTests(unittest.TestCase):
    def test_evaluation_and_monitoring_are_separate_jobs(self):
        evaluation = (ROOT / "resources/warranty_demo.job.yml").read_text(
            encoding="utf-8"
        )
        monitoring = (ROOT / "resources/warranty_monitoring.job.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("warranty_model_evaluation:", evaluation)
        self.assertNotIn("warranty_model_monitoring:", evaluation)
        self.assertIn("warranty_model_monitoring:", monitoring)
        self.assertIn("multilingual_warranty_qwen3_vs_labse.ipynb", evaluation)
        self.assertNotIn("05_monitoring_and_aiops.ipynb", evaluation)
        self.assertIn("05_monitoring_and_aiops.ipynb", monitoring)

    def test_evaluation_persists_a_queryable_scorecard(self):
        notebook = (
            ROOT / "src/notebooks/multilingual_warranty_qwen3_vs_labse.ipynb"
        ).read_text(encoding="utf-8")
        self.assertIn("comparison_metrics", notebook)
        self.assertIn("crosslingual_retrieval_accuracy", notebook)

    def test_readme_frames_monitoring_as_optional_extension(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Model Evaluation Accelerator", readme)
        self.assertIn("Optional operational extension", readme)
        self.assertNotIn("Two serverless notebook tasks", readme)

    def test_bundle_references_existing_assets(self):
        required = [
            ROOT / "databricks.yml",
            ROOT / "resources/warranty_demo.job.yml",
            ROOT / "resources/warranty_monitoring.job.yml",
            ROOT / "resources/warranty_monitoring.dashboard.yml",
            ROOT / "src/notebooks/multilingual_warranty_qwen3_vs_labse.ipynb",
            ROOT / "src/notebooks/05_monitoring_and_aiops.ipynb",
            ROOT / "src/dashboards/warranty_monitoring.lvdash.json",
            ROOT / "SETUP.md",
        ]
        for path in required:
            self.assertTrue(path.is_file(), str(path.relative_to(ROOT)))

    def test_dashboard_is_parameterized(self):
        path = ROOT / "src/dashboards/warranty_monitoring.lvdash.json"
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(dashboard["datasets"]), 6)
        for dataset in dashboard["datasets"]:
            query = " ".join(dataset["queryLines"])
            self.assertNotIn("akrishn_fe_dsa", query)
            self.assertNotRegex(
                query,
                r"\bFROM\s+`?[\w-]+`?\.`?[\w-]+`?\.",
            )

    def test_portable_files_have_no_personal_workspace_values(self):
        banned = [
            "akrishn_fe_dsa",
            "azure-aiquery",
            "adb-7405609619727450",
            "/Users/archana",
            "GM-AMA-demos",
        ]
        paths = [
            ROOT / "README.md",
            ROOT / "SETUP.md",
            ROOT / "databricks.yml",
            *NOTEBOOKS,
            ROOT / "src/dashboards/warranty_monitoring.lvdash.json",
            *sorted((ROOT / "resources").glob("*.yml")),
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for value in banned:
                self.assertNotIn(value, text, f"{value} found in {path.relative_to(ROOT)}")

    def test_readme_does_not_reference_missing_assets(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for relative in re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme):
            if "://" not in relative and not relative.startswith("#"):
                self.assertTrue((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
