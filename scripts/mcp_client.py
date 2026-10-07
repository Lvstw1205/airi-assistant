"""Bounded one-shot MCP client; JSON input/output, no model access to credentials."""
import asyncio,json,sys,os
from contextlib import AsyncExitStack
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
async def run(request):
    async with AsyncExitStack() as stack:
        server=request['server']
        if server['transport']=='stdio':
            streams=await stack.enter_async_context(stdio_client(StdioServerParameters(command=server['command'],args=server.get('args',[]),env={**os.environ,**server.get('env',{})})))
        else:
            streams=await stack.enter_async_context(streamablehttp_client(server['url'],headers=server.get('headers') or {}))
        session=await stack.enter_async_context(ClientSession(streams[0],streams[1]));await session.initialize()
        if request['op']=='list':
            result=await session.list_tools()
            return {'tools':[t.model_dump(mode='json') for t in result.tools],'next_cursor':result.nextCursor}
        result=await session.call_tool(request['tool'],request.get('arguments',{}))
        if result.isError:raise ValueError('MCP tool failed: '+' '.join(c.text for c in result.content if c.type=='text')[:500])
        if result.structuredContent is not None:return result.structuredContent
        texts=[c.text for c in result.content if c.type=='text']
        if len(texts)==1:
            try:return json.loads(texts[0])
            except ValueError:pass
        return {'text':'\n'.join(texts)[:16000]}
if __name__=='__main__':
    try:print(json.dumps({'result':asyncio.run(asyncio.wait_for(run(json.load(sys.stdin)),timeout=40))},ensure_ascii=False,allow_nan=False))
    except Exception as e:print(json.dumps({'error':str(e)[:600] or type(e).__name__}));sys.exit(1)
