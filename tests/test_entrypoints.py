import subprocess
import sys
import unittest

CHECK = """
import {module}
from sqlalchemy.orm import configure_mappers
from backend.common.base_model import Base

configure_mappers()
tables = [table.name for table in Base.metadata.sorted_tables]
assert "data_layers" in tables and "text2sql_ingestion_jobs" in tables, tables
"""


class EntrypointModelTests(unittest.TestCase):
    def check_in_clean_process(self, module: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", CHECK.format(module=module)], capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-800:])

    def test_worker_registers_every_model_on_its_own(self) -> None:
        self.check_in_clean_process("backend.modules.text2sql.worker")


if __name__ == "__main__":
    unittest.main()
