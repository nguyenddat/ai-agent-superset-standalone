from mcp.server import MCPServer

from .ask import register_ask_tools
from .column import register_column_tools
from .dataset import register_dataset_tools
from .expert_rule import register_expert_rule_tools
from .glossary import register_glossary_tools
from .join import register_join_tools
from .metric import register_metric_tools
from .own_knowledge import register_own_knowledge_tools
from .query import register_query_tools
from .table import register_table_tools


def register_tools(server: MCPServer) -> None:
    register_ask_tools(server)
    register_table_tools(server)
    register_join_tools(server)
    register_column_tools(server)
    register_metric_tools(server)
    register_glossary_tools(server)
    register_expert_rule_tools(server)
    register_own_knowledge_tools(server)
    register_query_tools(server)
    register_dataset_tools(server)
