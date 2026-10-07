"""AIRI's local, read-only MCP for Canada/US market research."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import market_data
mcp=FastMCP('airi_market_mcp')
read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=True)
@mcp.tool(annotations=read)
def market_exchange_rate(base:str='USD',quote:str='CAD',amount:float=1)->dict:
    """Daily reference exchange rate and deterministic conversion. Default 1 USD in CAD. Not an executable trading rate. ISO currency codes."""
    return market_data.exchange_rate(base,quote,amount)
@mcp.tool(annotations=read)
def market_quote(symbol:str)->dict:
    """Timestamped Yahoo stock/ETF quote and available valuation fields. Use AAPL for US or RY.TO for Toronto. Currency is always explicit; data may be delayed."""
    return market_data.quote(symbol)
@mcp.tool(annotations=read)
def market_search(query:str)->dict:
    """Resolve company/fund names to Canadian and US ticker candidates. Return candidates rather than assume a listing."""
    return market_data.search(query)
@mcp.tool(annotations=read)
def market_snapshot(symbol:str)->dict:
    """Quote plus last available regular-session five-minute prices for a watchlist sparkline. Chart session is explicitly dated."""
    return market_data.snapshot(symbol)
@mcp.tool(annotations=read)
def market_fundamentals(symbol:str)->dict:
    """Dated quarterly financial statements and provider valuation metrics. No inferred forecasts or AFFO."""
    return market_data.fundamentals(symbol)
if __name__=='__main__':mcp.run(transport='stdio')
